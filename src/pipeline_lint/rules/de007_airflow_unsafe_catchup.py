"""DE007 airflow-unsafe-catchup: catchup=True with a missing or moving start_date."""

from __future__ import annotations

import ast
from collections.abc import Iterator

from pipeline_lint.models import Severity, SourceFile, Violation
from pipeline_lint.parsing.airflow import (
    DagDefinition,
    is_airflow_code,
    iter_dag_definitions,
    resolve_value,
)
from pipeline_lint.parsing.python import AssignmentIndex
from pipeline_lint.rules.base import Rule
from pipeline_lint.rules.registry import register

# Calls whose result changes every time the DAG file is parsed.
DYNAMIC_METHODS = frozenset({"now", "utcnow", "today"})
DYNAMIC_FUNCTIONS = frozenset({"days_ago"})

FIX_HINT = "use a fixed, timezone-aware start_date or set catchup=False"


@register
class AirflowUnsafeCatchup(Rule):
    id = "DE007"
    name = "airflow-unsafe-catchup"
    severity = Severity.ERROR
    summary = "catchup=True with a missing or dynamic start_date causes unplanned backfills"
    rationale = (
        "With catchup enabled, the scheduler creates one run for every interval between "
        "start_date and now that has not run yet. If start_date is missing, comes from "
        "datetime.now() or days_ago(), it moves every time the file is parsed, so the set "
        "of runs Airflow creates is unpredictable. Combined with non-idempotent tasks, the "
        "resulting surprise backfill writes duplicated or inconsistent data."
    )
    bad_example = (
        "with DAG(\n"
        "    dag_id='sync_orders',\n"
        "    schedule='@daily',\n"
        "    start_date=datetime.now() - timedelta(days=7),\n"
        "    catchup=True,\n"
        ") as dag:\n"
        "    ..."
    )
    good_example = (
        "with DAG(\n"
        "    dag_id='sync_orders',\n"
        "    schedule='@daily',\n"
        "    start_date=pendulum.datetime(2026, 1, 1, tz='UTC'),\n"
        "    catchup=True,\n"
        ") as dag:\n"
        "    ..."
    )

    def check_python(self, source: SourceFile) -> Iterator[Violation]:
        tree = source.python_ast
        if tree is None or not is_airflow_code(tree):
            return

        assignments = AssignmentIndex(tree)
        for dag in iter_dag_definitions(tree):
            catchup = dag.keywords.get("catchup")
            if not (isinstance(catchup, ast.Constant) and catchup.value is True):
                continue
            problem = _start_date_problem(dag, assignments)
            if problem is None:
                continue
            yield self.violation(
                source,
                line=catchup.lineno,
                column=source.char_column(catchup.lineno, catchup.col_offset),
                message=f"catchup=True with {problem}; {FIX_HINT}",
            )


def _start_date_problem(dag: DagDefinition, assignments: AssignmentIndex) -> str | None:
    start_date = dag.setting("start_date")
    if start_date is None:
        # start_date may live in default_args we cannot see: do not guess.
        return "no start_date" if dag.default_args_known else None

    value = resolve_value(start_date, assignments, start_date.lineno)
    for node in ast.walk(value):
        if isinstance(node, ast.Call) and _is_dynamic_call(node):
            return f"a start_date that changes on every parse ({ast.unparse(node)})"
    return None


def _is_dynamic_call(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr in DYNAMIC_METHODS or func.attr in DYNAMIC_FUNCTIONS
    return isinstance(func, ast.Name) and func.id in DYNAMIC_FUNCTIONS

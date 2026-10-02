"""DE006 airflow-missing-retries: a DAG that fails for good on the first transient error."""

from __future__ import annotations

import ast
from collections.abc import Iterator

from pipeline_lint.models import Severity, SourceFile, Violation
from pipeline_lint.parsing.airflow import is_airflow_code, iter_dag_definitions
from pipeline_lint.rules.base import Rule
from pipeline_lint.rules.registry import register

FIX_HINT = (
    'set "retries" and "retry_delay" in default_args '
    "(retries are only safe when tasks are idempotent, see DE001)"
)


@register
class AirflowMissingRetries(Rule):
    id = "DE006"
    name = "airflow-missing-retries"
    severity = Severity.WARNING
    summary = "Airflow DAG without retries turns every transient failure into a failed run"
    rationale = (
        "Network blips, warehouse locks, API rate limits and spot-instance losses are normal "
        "in production. Airflow's default is zero retries, so each of them fails the task, "
        "blocks downstream tasks and waits for a human to clear it, often outside working "
        "hours. A few retries with a delay absorb these failures automatically."
    )
    bad_example = (
        "with DAG(\n"
        "    dag_id='ingest_orders',\n"
        "    default_args={'owner': 'data-team'},\n"
        "    schedule='@daily',\n"
        "    start_date=pendulum.datetime(2026, 1, 1, tz='UTC'),\n"
        ") as dag:\n"
        "    ..."
    )
    good_example = (
        "default_args = {\n"
        "    'owner': 'data-team',\n"
        "    'retries': 3,\n"
        "    'retry_delay': timedelta(minutes=5),\n"
        "}\n"
        "with DAG(dag_id='ingest_orders', default_args=default_args, ...) as dag:\n"
        "    ..."
    )

    def check_python(self, source: SourceFile) -> Iterator[Violation]:
        tree = source.python_ast
        if tree is None or not is_airflow_code(tree):
            return

        for dag in iter_dag_definitions(tree):
            if not dag.default_args_known:
                continue
            retries = dag.default_args.get("retries")
            if retries is None:
                problem = "DAG has no retries in default_args"
            elif isinstance(retries, ast.Constant) and retries.value == 0:
                problem = "DAG sets retries to 0"
            else:
                continue
            yield self.violation(
                source,
                line=dag.line,
                column=source.char_column(dag.line, dag.byte_col),
                message=f"{problem}, so any transient failure fails the run; {FIX_HINT}",
            )

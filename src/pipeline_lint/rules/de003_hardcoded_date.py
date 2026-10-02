"""DE003 hardcoded-date: a literal date in a filter makes a scheduled job use a fixed window."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator

from sqlglot import exp

from pipeline_lint.models import Severity, SourceFile, Violation
from pipeline_lint.parsing.python import is_spark_code, iter_method_calls
from pipeline_lint.rules.base import Rule
from pipeline_lint.rules.registry import register

# A valid calendar date, optionally with a time and a timezone: 2026-01-01, 2026-01-01 08:30,
# 2026-01-01T08:30:00.000Z. Month and day ranges are checked to avoid matching IDs and versions.
_DATE = (
    r"\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])"
    r"(?:[ T](?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d+)?)?)?"
    r"(?:Z|[+-]\d{2}:?\d{2})?"
)
DATE_LITERAL = re.compile(_DATE)
# A quoted date inside a SQL expression string, e.g. .where("order_date >= '2026-01-01'").
QUOTED_DATE = re.compile(rf"""['"]({_DATE})['"]""")

# Placeholder dates with a fixed meaning, common in SCD Type 2 tables ("valid until forever").
SENTINEL_DATES = frozenset({"0001-01-01", "1900-01-01", "1970-01-01", "2999-12-31", "9999-12-31"})

# SQL comparisons whose operands are checked, and the clauses that make them a filter.
SQL_COMPARISONS = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between, exp.In)
SQL_FILTER_CLAUSES = (exp.Where, exp.Having, exp.Qualify, exp.Join)

# PySpark methods whose arguments are filter conditions or bounds.
PYSPARK_FILTER_METHODS = frozenset({"filter", "where", "between"})

# Calls that build a date in Python: date(2026, 1, 1), datetime.datetime(2026, 1, 1, 8, 0).
DATE_CONSTRUCTORS = frozenset({"date", "datetime"})

FIX_HINT = "use the run's logical date (e.g. {{ ds }}) or a job parameter"


def is_hardcoded_date(text: str) -> bool:
    """True for a literal that is a real calendar date and not a well-known sentinel."""
    text = text.strip()
    return DATE_LITERAL.fullmatch(text) is not None and text[:10] not in SENTINEL_DATES


@register
class HardcodedDate(Rule):
    id = "DE003"
    name = "hardcoded-date"
    severity = Severity.WARNING
    summary = "Hardcoded date in a filter makes a scheduled job process the wrong window"
    rationale = (
        "A filter such as order_date = '2026-01-01' is correct on the day the query is "
        "written and wrong on every run after it. Scheduled runs keep reprocessing the same "
        "day, and backfills cannot target other days. Nothing fails, so the problem is only "
        "noticed when someone asks why the dashboard stopped changing. Assistants often "
        "produce such filters because the example in the prompt contained a concrete date."
    )
    bad_example = (
        "SELECT * FROM silver.orders WHERE order_date = '2026-01-01'\n\n"
        "orders.filter(F.col('order_date') >= '2026-01-01')"
    )
    good_example = (
        "SELECT * FROM silver.orders WHERE order_date = '{{ ds }}'\n\n"
        "run_date = spark.conf.get('pipeline.run_date')\n"
        "orders.filter(F.col('order_date') == run_date)"
    )

    # --- SQL -------------------------------------------------------------------------------

    def check_sql(self, source: SourceFile) -> Iterator[Violation]:
        for statement in source.sql_statements:
            used: set[tuple[int, int]] = set()
            for value in _sql_filter_dates(statement.expression):
                position = _locate(source, value, (statement.line, 1), used)
                line, column = position or (statement.line, statement.column)
                yield self.violation(
                    source,
                    line=line,
                    column=column,
                    message=f"Hardcoded date '{value}' in a filter; {FIX_HINT}",
                )

    # --- PySpark -----------------------------------------------------------------------------

    def check_python(self, source: SourceFile) -> Iterator[Violation]:
        tree = source.python_ast
        if tree is None or not is_spark_code(tree, source.kind):
            return

        reported: set[int] = set()
        for call, _attr in iter_method_calls(tree, PYSPARK_FILTER_METHODS):
            arguments = [*call.args, *(kw.value for kw in call.keywords)]
            for argument in arguments:
                for node in ast.walk(argument):
                    value = _python_date(node)
                    if value is None or id(node) in reported:
                        continue
                    reported.add(id(node))
                    yield self.violation(
                        source,
                        line=node.lineno,
                        column=source.char_column(node.lineno, node.col_offset),
                        message=f"Hardcoded date {value} in a filter; {FIX_HINT}",
                    )


def _sql_filter_dates(expression: exp.Expression) -> Iterator[str]:
    """String literals that are dates and are compared inside WHERE / ON / HAVING / QUALIFY."""
    seen: set[int] = set()
    for comparison in expression.find_all(*SQL_COMPARISONS):
        if comparison.find_ancestor(*SQL_FILTER_CLAUSES) is None:
            continue
        for operand in comparison.iter_expressions():
            for literal in operand.find_all(exp.Literal):
                if id(literal) in seen or not literal.is_string:
                    continue
                seen.add(id(literal))
                if is_hardcoded_date(literal.this):
                    yield literal.this


def _locate(
    source: SourceFile, value: str, start: tuple[int, int], used: set[tuple[int, int]]
) -> tuple[int, int] | None:
    """Find the next occurrence of ``value`` that has not been reported yet."""
    position = source.find_text(value, start)
    while position is not None and position in used:
        position = source.find_text(value, (position[0], position[1] + 1))
    if position is not None:
        used.add(position)
    return position


def _python_date(node: ast.AST) -> str | None:
    """A printable description if ``node`` is a hardcoded date, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if is_hardcoded_date(node.value):
            return f"'{node.value.strip()}'"
        # A SQL expression string: .where("order_date >= '2026-01-01'")
        for match in QUOTED_DATE.finditer(node.value):
            if is_hardcoded_date(match.group(1)):
                return f"'{match.group(1)}'"
        return None

    if isinstance(node, ast.Call):
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name in DATE_CONSTRUCTORS and len(node.args) >= 3:
            parts = node.args[:3]
            if all(isinstance(p, ast.Constant) and isinstance(p.value, int) for p in parts):
                return ast.unparse(node)
    return None

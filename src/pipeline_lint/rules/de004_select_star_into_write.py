"""DE004 select-star-into-write: SELECT * decides the columns of a table write."""

from __future__ import annotations

import ast
from collections.abc import Iterator

from sqlglot import exp

from pipeline_lint.models import Severity, SourceFile, Violation
from pipeline_lint.parsing.python import (
    attribute_name_position,
    chained_calls,
    is_spark_code,
    iter_method_calls,
    parent_map,
)
from pipeline_lint.parsing.sql import TableName, insert_target
from pipeline_lint.rules.base import Rule
from pipeline_lint.rules.registry import register

# Writer entry points: `df.select("*").write...` or `df.select("*").writeTo(...)`.
WRITE_ENTRY_POINTS = frozenset({"write", "writeTo"})


@register
class SelectStarIntoWrite(Rule):
    id = "DE004"
    name = "select-star-into-write"
    severity = Severity.WARNING
    summary = "SELECT * decides which columns are written to a table"
    rationale = (
        "With SELECT * the written columns are whatever the upstream table has today. "
        "INSERT matches columns by position, so when a column is added, removed or reordered "
        "upstream, the load either fails or silently writes values into the wrong columns. "
        "CREATE TABLE AS SELECT * copies every upstream change into the new table, including "
        "columns nobody reviewed, such as newly added personal data. Listing columns makes "
        "the table's contract explicit and turns upstream changes into visible errors."
    )
    bad_example = "INSERT INTO analytics.fct_orders\nSELECT * FROM staging.orders;"
    good_example = (
        "INSERT INTO analytics.fct_orders (order_id, customer_id, amount, order_date)\n"
        "SELECT order_id, customer_id, amount, order_date FROM staging.orders;"
    )

    # --- SQL -------------------------------------------------------------------------------

    def check_sql(self, source: SourceFile) -> Iterator[Violation]:
        for statement in source.sql_statements:
            for message in _sql_findings(statement.expression):
                yield self.violation(
                    source, line=statement.line, column=statement.column, message=message
                )

    # --- PySpark -----------------------------------------------------------------------------

    def check_python(self, source: SourceFile) -> Iterator[Violation]:
        tree = source.python_ast
        if tree is None or not is_spark_code(tree, source.kind):
            return

        parents = parent_map(tree)
        for call, attr in iter_method_calls(tree, {"select"}):
            if not _selects_star(call):
                continue
            if not any(link.name in WRITE_ENTRY_POINTS for link in chained_calls(call, parents)):
                continue
            line, byte_col = attribute_name_position(attr)
            yield self.violation(
                source,
                line=line,
                column=source.char_column(line, byte_col),
                message=(
                    '.select("*") before a write passes every upstream column through; '
                    "select the columns explicitly"
                ),
            )


def _sql_findings(expression: exp.Expression) -> Iterator[str]:
    for insert in expression.find_all(exp.Insert):
        table = insert_target(insert)
        query = insert.expression
        if table is None or query is None or insert.args.get("by_name"):
            continue
        if _projects_star(query):
            yield (
                f"SELECT * feeds INSERT INTO {_name(table)}: columns are matched by position, "
                "so an upstream column change fails the load or shifts values into the wrong "
                "columns; list the columns explicitly"
            )

    for create in expression.find_all(exp.Create):
        if str(create.args.get("kind", "")).upper() != "TABLE":
            continue
        query = create.expression
        target = create.this.this if isinstance(create.this, exp.Schema) else create.this
        if query is None or not isinstance(target, exp.Table):
            continue
        if _projects_star(query):
            yield (
                f"SELECT * in CREATE TABLE {_name(target)} AS: the table silently inherits "
                "every upstream column change; list the columns explicitly"
            )


def _projects_star(query: exp.Expression) -> bool:
    """True if the columns produced by ``query`` come from ``*`` or ``alias.*``.

    Only the final projection counts (each branch of a UNION). Stars in subqueries, CTEs,
    EXISTS (...) or COUNT(*) do not decide which columns are written.
    """
    if isinstance(query, exp.Subquery):
        return _projects_star(query.this)
    if isinstance(query, exp.Select):
        return any(_is_star(projection) for projection in query.expressions)
    if isinstance(query, (exp.Union, exp.Except, exp.Intersect)):
        return _projects_star(query.this) or _projects_star(query.expression)
    return False


def _is_star(projection: exp.Expression) -> bool:
    if isinstance(projection, exp.Star):
        return True
    return isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star)


def _selects_star(call: ast.Call) -> bool:
    """``.select("*")`` or ``.select("alias.*")``, also next to other columns."""
    return any(
        isinstance(argument, ast.Constant)
        and isinstance(argument.value, str)
        and (argument.value == "*" or argument.value.endswith(".*"))
        for argument in call.args
    )


def _name(table: exp.Table) -> str:
    name = TableName.from_table(table)
    return str(name) if name else table.sql()

"""DE001 non-idempotent-append: writes that add the same rows again when a job is re-run."""

from __future__ import annotations

import ast
from collections.abc import Iterator

from sqlglot import exp

from pipeline_lint.models import Severity, SourceFile, Violation
from pipeline_lint.parsing.python import (
    AssignmentIndex,
    ChainLink,
    attribute_name_position,
    chained_calls,
    is_spark_code,
    iter_method_calls,
    parent_map,
    receiver_chain,
    string_arg,
)
from pipeline_lint.parsing.sql import TableName, cleared_tables, insert_target
from pipeline_lint.rules.base import Rule
from pipeline_lint.rules.registry import register

# INSERT variants that are idempotent by construction:
#   overwrite   INSERT OVERWRITE
#   conflict    INSERT ... ON CONFLICT / ON DUPLICATE KEY UPDATE
#   alternative INSERT OR REPLACE / INSERT OR IGNORE
#   ignore      INSERT IGNORE
#   where       INSERT INTO ... REPLACE WHERE (Databricks)
IDEMPOTENT_INSERT_ARGS = ("overwrite", "conflict", "alternative", "ignore", "where")

# DataFrameWriter calls that name the target table in their first argument.
TABLE_WRITE_METHODS = frozenset({"saveAsTable", "insertInto"})

FIX_HINT = "use MERGE, overwrite only the processed partition, or delete that window first"


@register
class NonIdempotentAppend(Rule):
    id = "DE001"
    name = "non-idempotent-append"
    severity = Severity.ERROR
    summary = "Append-only write duplicates data when the job is retried or re-run"
    rationale = (
        "Pipelines are re-run all the time: the orchestrator retries a task after a timeout, "
        "an engineer re-runs a failed day, a backfill replays a month. A plain INSERT INTO or "
        "an append-mode write adds the same rows again on every run, silently producing "
        "duplicates and double-counted metrics. An idempotent write gives the same result "
        "whether it runs once or five times."
    )
    bad_example = (
        "INSERT INTO analytics.fct_orders\n"
        "SELECT * FROM raw.orders WHERE order_date = '{{ ds }}';\n\n"
        "df.write.mode('append').saveAsTable('analytics.fct_orders')"
    )
    good_example = (
        "MERGE INTO analytics.fct_orders AS t\n"
        "USING staged_orders AS s ON t.order_id = s.order_id\n"
        "WHEN MATCHED THEN UPDATE SET *\n"
        "WHEN NOT MATCHED THEN INSERT *;\n\n"
        "(df.write.format('delta').mode('overwrite')\n"
        "   .option('replaceWhere', \"order_date = '2026-01-01'\")\n"
        "   .saveAsTable('analytics.fct_orders'))"
    )

    # --- SQL -------------------------------------------------------------------------------

    def check_sql(self, source: SourceFile) -> Iterator[Violation]:
        cleared: list[TableName] = []
        for statement in source.sql_statements:
            cleared.extend(cleared_tables(statement.expression))

            for insert in statement.expression.find_all(exp.Insert):
                if any(insert.args.get(arg) for arg in IDEMPOTENT_INSERT_ARGS):
                    continue
                table = insert_target(insert)
                name = TableName.from_table(table) if table is not None else None
                if name is None or any(name.matches(done) for done in cleared):
                    continue
                yield self.violation(
                    source,
                    line=statement.line,
                    column=statement.column,
                    message=(
                        f"INSERT INTO {name} appends rows: re-running this job inserts them "
                        f"again; {FIX_HINT}"
                    ),
                )

    # --- PySpark -----------------------------------------------------------------------------

    def check_python(self, source: SourceFile) -> Iterator[Violation]:
        tree = source.python_ast
        if tree is None or not is_spark_code(tree, source.kind):
            return

        assignments = AssignmentIndex(tree)
        parents = parent_map(tree)
        # (line, table) for every DELETE/TRUNCATE in spark.sql() calls or %sql cells.
        cleared = [
            (statement.line, name)
            for statement in source.sql_statements
            for name in cleared_tables(statement.expression)
        ]

        for call, attr in iter_method_calls(tree, {"mode", "insertInto", "append"}):
            chain = receiver_chain(call, assignments)
            names = {link.name for link in chain}
            if "writeStream" in names:
                # Streaming appends are made exactly-once by the checkpoint, not by the write.
                continue

            target = _append_target(call, attr, chain, names, parents)
            if target is None:
                continue
            description, table = target

            line, byte_col = attribute_name_position(attr)
            if table is not None and any(
                done_line < line and table.matches(done) for done_line, done in cleared
            ):
                continue

            yield self.violation(
                source,
                line=line,
                column=source.char_column(line, byte_col),
                message=(
                    f"{description} appends rows: re-running this job writes them again; {FIX_HINT}"
                ),
            )


def _append_target(
    call: ast.Call,
    attr: ast.Attribute,
    chain: list[ChainLink],
    names: set[str],
    parents: dict[ast.AST, ast.AST],
) -> tuple[str, TableName | None] | None:
    """If ``call`` is an append write, return ``(description, target table if known)``."""
    if attr.attr == "mode":
        # df.write...mode("append")
        mode = string_arg(call, 0, keyword="saveMode")
        if "write" not in names or mode is None or mode.lower() != "append":
            return None
        table = next(
            (
                string_arg(link.call)
                for link in chained_calls(call, parents)
                if link.name in TABLE_WRITE_METHODS and link.call is not None
            ),
            None,
        )
        return '.mode("append")', _table(table)

    if attr.attr == "insertInto":
        # df.write.insertInto("t") appends unless overwrite=True. If .mode(...) is set
        # explicitly, the append case is already reported at the .mode() call.
        if "write" not in names or "mode" in names or _overwrite_requested(call):
            return None
        return ".insertInto()", _table(string_arg(call))

    if attr.attr == "append":
        # df.writeTo("t").append()  (DataFrameWriterV2)
        writer = next((link for link in chain if link.name == "writeTo"), None)
        if writer is None or call.args or call.keywords:
            return None
        table = string_arg(writer.call) if writer.call is not None else None
        return ".writeTo(...).append()", _table(table)

    return None


def _overwrite_requested(call: ast.Call) -> bool:
    """True for ``insertInto(t, True)`` or ``insertInto(t, overwrite=True)``."""
    candidates = call.args[1:2] + [kw.value for kw in call.keywords if kw.arg == "overwrite"]
    return any(isinstance(node, ast.Constant) and node.value is True for node in candidates)


def _table(name: str | None) -> TableName | None:
    return TableName.from_string(name) if name else None

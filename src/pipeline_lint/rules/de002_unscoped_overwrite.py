"""DE002 unscoped-overwrite: an overwrite meant for one slice of data replaces the whole table."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator

from sqlglot import exp

from pipeline_lint.models import Severity, SourceFile, Violation
from pipeline_lint.parsing.python import (
    AssignmentIndex,
    ChainLink,
    attribute_name_position,
    chained_calls,
    insert_into_overwrite,
    is_spark_code,
    iter_method_calls,
    parent_map,
    receiver_chain,
    string_arg,
)
from pipeline_lint.parsing.sql import TableName, insert_target
from pipeline_lint.rules.base import Rule
from pipeline_lint.rules.registry import register

# Session-wide dynamic partition overwrite, set anywhere in the file:
#   spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
#   SparkSession.builder.config("spark.sql.sources.partitionOverwriteMode", "dynamic")
#   SET spark.sql.sources.partitionOverwriteMode = dynamic;
DYNAMIC_MODE_SETTING = re.compile(r"sources\.partitionOverwriteMode\W{0,6}dynamic", re.IGNORECASE)

FIX_HINT = 'scope it with .option("replaceWhere", ...) or dynamic partition overwrite'
PARTITION_BY_NOTE = (
    " (.partitionBy() alone does not limit an overwrite under Spark's default static mode)"
)


@register
class UnscopedOverwrite(Rule):
    id = "DE002"
    name = "unscoped-overwrite"
    severity = Severity.WARNING
    summary = "Overwrite without a partition scope replaces the entire table"
    rationale = (
        "A daily job usually means to refresh one day of data. An overwrite without a scope "
        "deletes every row in the table and keeps only what this run produced, so history "
        "disappears the first time the job runs. A common trap: adding .partitionBy() does "
        "not help. Under Spark's default 'static' partition overwrite mode, all partitions "
        "are still replaced. Only replaceWhere (Delta), dynamic partition overwrite, or an "
        "explicit PARTITION clause limits what gets deleted."
    )
    bad_example = (
        "(daily.write.format('delta').mode('overwrite')\n"
        "   .partitionBy('order_date')\n"
        "   .saveAsTable('gold.daily_sales'))"
    )
    good_example = (
        "(daily.write.format('delta').mode('overwrite')\n"
        "   .option('replaceWhere', f\"order_date = '{run_date}'\")\n"
        "   .saveAsTable('gold.daily_sales'))\n\n"
        "INSERT OVERWRITE TABLE gold.daily_sales PARTITION (order_date = '{{ ds }}')\n"
        "SELECT ..."
    )

    # --- SQL -------------------------------------------------------------------------------

    def check_sql(self, source: SourceFile) -> Iterator[Violation]:
        if DYNAMIC_MODE_SETTING.search(source.text):
            return
        for statement in source.sql_statements:
            for insert in statement.expression.find_all(exp.Insert):
                if not insert.args.get("overwrite") or _has_partition_clause(insert):
                    continue
                table = insert_target(insert)
                name = TableName.from_table(table) if table is not None else None
                if name is None:  # e.g. INSERT OVERWRITE DIRECTORY
                    continue
                yield self.violation(
                    source,
                    line=statement.line,
                    column=statement.column,
                    message=(
                        f"INSERT OVERWRITE {name} without a PARTITION clause replaces the whole "
                        "table; add PARTITION (...) or enable dynamic partition overwrite"
                    ),
                )

    # --- PySpark -----------------------------------------------------------------------------

    def check_python(self, source: SourceFile) -> Iterator[Violation]:
        tree = source.python_ast
        if tree is None or not is_spark_code(tree, source.kind):
            return
        if DYNAMIC_MODE_SETTING.search(source.text):
            return

        assignments = AssignmentIndex(tree)
        parents = parent_map(tree)

        for call, attr in iter_method_calls(tree, {"mode", "insertInto"}):
            before = receiver_chain(call, assignments)
            names = {link.name for link in before}
            if "writeStream" in names or "write" not in names:
                continue

            if attr.attr == "mode":
                mode = string_arg(call, 0, keyword="saveMode")
                if mode is None or mode.lower() != "overwrite":
                    continue
                description = '.mode("overwrite")'
            else:
                # insertInto(t, overwrite=True). With an explicit .mode(...) in the chain,
                # the overwrite case is already reported at the .mode() call.
                if "mode" in names or not insert_into_overwrite(call):
                    continue
                description = ".insertInto(..., overwrite=True)"

            links = before + list(chained_calls(call, parents))
            if _is_scoped(links):
                continue

            note = PARTITION_BY_NOTE if any(link.name == "partitionBy" for link in links) else ""
            line, byte_col = attribute_name_position(attr)
            yield self.violation(
                source,
                line=line,
                column=source.char_column(line, byte_col),
                message=f"{description} replaces the whole table, not just this run's data; "
                f"{FIX_HINT}{note}",
            )


def _has_partition_clause(insert: exp.Insert) -> bool:
    """True for ``INSERT OVERWRITE TABLE t PARTITION (...)``.

    Depending on the dialect, sqlglot attaches the PARTITION clause to the target table or
    to the INSERT itself, so both places are checked. The SELECT part is not searched.
    """
    if insert.args.get("partition"):
        return True
    target = insert.this
    return target is not None and target.find(exp.Partition) is not None


def _is_scoped(links: list[ChainLink]) -> bool:
    """True if the writer chain limits the overwrite with replaceWhere or dynamic mode."""
    for link in links:
        if link.call is None:
            continue
        if link.name == "option":
            key = (string_arg(link.call, 0) or "").lower()
            value = (string_arg(link.call, 1) or "").lower()
            if key == "replacewhere" or (key == "partitionoverwritemode" and value == "dynamic"):
                return True
        elif link.name == "options":
            for keyword in link.call.keywords:
                key = (keyword.arg or "").lower()
                value = keyword.value
                if key == "replacewhere":
                    return True
                if (
                    key == "partitionoverwritemode"
                    and isinstance(value, ast.Constant)
                    and str(value.value).lower() == "dynamic"
                ):
                    return True
    return False

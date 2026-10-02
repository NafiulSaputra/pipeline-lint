"""DE005 driver-collect: ``.collect()`` / ``.toPandas()`` on an unbounded DataFrame."""

from __future__ import annotations

from collections.abc import Iterator

from pipeline_lint.models import Severity, SourceFile, Violation
from pipeline_lint.parsing.python import (
    AssignmentIndex,
    attribute_name_position,
    imports_module,
    iter_method_calls,
    receiver_methods,
)
from pipeline_lint.rules.base import Rule
from pipeline_lint.rules.registry import register

DRIVER_ACTIONS = frozenset({"collect", "toPandas"})

# Upstream methods that bound the size of the result.
BOUNDING_METHODS = frozenset({"limit"})

# `.agg()` without grouping is a global aggregate: exactly one row, safe to collect.
# With grouping it returns one row per group, which can be arbitrarily large.
GROUPING_METHODS = frozenset({"groupBy", "groupby", "rollup", "cube"})

# Modules whose presence marks a file as Spark code.
SPARK_MODULES = ("pyspark", "databricks.connect")


@register
class DriverCollect(Rule):
    id = "DE005"
    name = "driver-collect"
    severity = Severity.WARNING
    summary = "collect() / toPandas() pulls an unbounded DataFrame into driver memory"
    rationale = (
        "Spark keeps data distributed across executors. collect() and toPandas() copy every "
        "row into the memory of a single driver process. On development samples this works; "
        "at production volume the driver runs out of memory and the job fails, often hours "
        "into a run. Generated code frequently collects only to loop over rows in Python, "
        "which also throws away Spark's parallelism."
    )
    bad_example = (
        "for row in orders.select('customer_id').distinct().collect():\n"
        "    process(row['customer_id'])"
    )
    good_example = (
        "# Keep the work distributed\n"
        "orders.join(customers, 'customer_id').write.saveAsTable('analytics.orders_enriched')\n\n"
        "# Or bound the result explicitly\n"
        "preview = orders.limit(100).toPandas()"
    )

    def check_python(self, source: SourceFile) -> Iterator[Violation]:
        tree = source.python_ast
        if tree is None or not _is_spark_code(source):
            return

        assignments = AssignmentIndex(tree)
        for call, attr in iter_method_calls(tree, DRIVER_ACTIONS):
            # DataFrame.collect() and toPandas() take no arguments; a call with arguments
            # is some other object's method that happens to share the name.
            if call.args or call.keywords:
                continue

            upstream = set(receiver_methods(call, assignments))
            if upstream & BOUNDING_METHODS:
                continue
            if "agg" in upstream and not upstream & GROUPING_METHODS:
                continue

            line, byte_col = attribute_name_position(attr)
            yield self.violation(
                source,
                line=line,
                column=source.char_column(line, byte_col),
                message=(
                    f".{attr.attr}() loads the entire DataFrame into driver memory; "
                    "keep the work distributed or bound it with .limit(n) first"
                ),
            )


def _is_spark_code(source: SourceFile) -> bool:
    # Databricks notebooks get a ready-made `spark` session and usually import nothing.
    if source.kind == "databricks_notebook":
        return True
    assert source.python_ast is not None
    return any(imports_module(source.python_ast, module) for module in SPARK_MODULES)

"""SQL embedded in Python: ``spark.sql("...")`` calls."""

from __future__ import annotations

import ast
from collections.abc import Iterator

from pipeline_lint.parsing.python import AssignmentIndex, iter_method_calls


def iter_embedded_sql(tree: ast.Module) -> Iterator[tuple[str, int]]:
    """Yield ``(sql_text, first_line)`` for every ``<session>.sql(<string>)`` call.

    The argument may be a string literal or a variable assigned a string literal earlier in
    the module (``query = \"\"\"...\"\"\"`` then ``spark.sql(query)``), a common pattern in
    generated code. f-strings and concatenations are skipped: their final text is only known
    at runtime.
    """
    assignments = AssignmentIndex(tree)
    for call, _attr in iter_method_calls(tree, {"sql"}):
        if not call.args:
            continue
        argument = call.args[0]
        if isinstance(argument, ast.Name):
            assignment = assignments.latest_before(argument.id, call.lineno)
            if assignment is None:
                continue
            argument = assignment.value
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            yield argument.value, argument.lineno

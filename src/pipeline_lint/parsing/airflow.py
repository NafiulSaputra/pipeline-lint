"""Find Airflow DAG definitions in a Python AST."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass, field

from pipeline_lint.parsing.python import AssignmentIndex, attribute_name_position, imports_module

# DAG() class (Airflow 2 and 3) and the @dag decorator.
DAG_CALLABLES = frozenset({"DAG", "dag"})

_MAX_RESOLVE_DEPTH = 5


@dataclass(frozen=True)
class DagDefinition:
    """One ``DAG(...)``, ``with DAG(...)``, ``@dag(...)`` or bare ``@dag``."""

    line: int
    byte_col: int
    keywords: dict[str, ast.expr]
    # Keys of default_args, when they can be determined statically.
    default_args: dict[str, ast.expr] = field(default_factory=dict)
    # False when default_args comes from somewhere the linter cannot see (an import,
    # a function call, ``{**base}``). Rules should not guess in that case.
    default_args_known: bool = True

    def setting(self, name: str) -> ast.expr | None:
        """A DAG argument, falling back to the same key in default_args."""
        return self.keywords.get(name) or self.default_args.get(name)


def is_airflow_code(tree: ast.Module) -> bool:
    return imports_module(tree, "airflow")


def iter_dag_definitions(tree: ast.Module) -> Iterator[DagDefinition]:
    """Yield every DAG definition in ``tree``."""
    assignments = AssignmentIndex(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_dag_callable(node.func):
            keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
            if any(kw.arg is None for kw in node.keywords):  # DAG(**config)
                yield _definition(node.func, keywords, None, assignments, known=False)
                continue
            yield _definition(node.func, keywords, keywords.get("default_args"), assignments)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if _is_dag_callable(decorator):  # bare @dag without arguments
                    yield _definition(decorator, {}, None, assignments)


def _is_dag_callable(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id in DAG_CALLABLES
    return isinstance(node, ast.Attribute) and node.attr in DAG_CALLABLES


def _definition(
    func: ast.expr,
    keywords: dict[str, ast.expr],
    default_args: ast.expr | None,
    assignments: AssignmentIndex,
    *,
    known: bool = True,
) -> DagDefinition:
    if isinstance(func, ast.Attribute):
        line, byte_col = attribute_name_position(func)
    else:
        line, byte_col = func.lineno, func.col_offset

    if not known:
        return DagDefinition(line, byte_col, keywords, default_args_known=False)
    if default_args is None:
        return DagDefinition(line, byte_col, keywords)

    resolved = resolve_mapping(default_args, assignments, line)
    if resolved is None:
        return DagDefinition(line, byte_col, keywords, default_args_known=False)
    return DagDefinition(line, byte_col, keywords, default_args=resolved)


def resolve_value(node: ast.expr, assignments: AssignmentIndex, line: int) -> ast.expr:
    """Follow a plain variable to the expression it was last assigned, if any."""
    depth = 0
    while isinstance(node, ast.Name) and depth < _MAX_RESOLVE_DEPTH:
        assignment = assignments.latest_before(node.id, line)
        if assignment is None:
            break
        node, line = assignment.value, assignment.lineno
        depth += 1
    return node


def resolve_mapping(
    node: ast.expr, assignments: AssignmentIndex, line: int
) -> dict[str, ast.expr] | None:
    """Turn a dict literal or ``dict(key=value)`` call into ``{key: value}``.

    Returns None when the contents cannot be known statically: an imported name,
    ``{**base, ...}``, ``dict(**base)``, or any other expression.
    """
    node = resolve_value(node, assignments, line)
    if isinstance(node, ast.Dict):
        mapping: dict[str, ast.expr] = {}
        for key, value in zip(node.keys, node.values, strict=True):
            if key is None:  # {**base}
                return None
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                mapping[key.value] = value
        return mapping
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dict"
        and not node.args
        and all(kw.arg is not None for kw in node.keywords)
    ):
        return {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
    return None

"""Helpers for inspecting Python ASTs. Shared by every rule that checks Python code."""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Collection, Iterator
from typing import NamedTuple

# Guards against pathological assignment chains (a = b; b = c; ...).
_MAX_RESOLVE_DEPTH = 10


def imports_module(tree: ast.Module, module: str) -> bool:
    """Return True if ``tree`` imports ``module`` or a submodule of it (absolute imports only)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(_is_same_or_submodule(alias.name, module) for alias in node.names):
                return True
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module is not None
            and _is_same_or_submodule(node.module, module)
        ):
            return True
    return False


def _is_same_or_submodule(name: str, module: str) -> bool:
    return name == module or name.startswith(module + ".")


def iter_method_calls(
    tree: ast.AST, method_names: Collection[str]
) -> Iterator[tuple[ast.Call, ast.Attribute]]:
    """Yield ``(call, attribute)`` for every call of the form ``<expr>.<name>(...)``."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in method_names
        ):
            yield node, node.func


class Assignment(NamedTuple):
    lineno: int
    value: ast.expr


class AssignmentIndex:
    """Index of simple ``name = <expr>`` assignments, used to follow DataFrame variables.

    Deliberately simple: it ignores scopes (functions, classes) and control flow, and only
    tracks plain names. That is enough for typical linear pipeline scripts and notebooks.
    """

    def __init__(self, tree: ast.AST) -> None:
        by_name: defaultdict[str, list[Assignment]] = defaultdict(list)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        by_name[target.id].append(Assignment(node.lineno, node.value))
            elif (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.value is not None
            ):
                by_name[node.target.id].append(Assignment(node.lineno, node.value))
        self._by_name = dict(by_name)

    def latest_before(self, name: str, line: int) -> Assignment | None:
        """The most recent assignment to ``name`` that starts before ``line``."""
        candidates = [a for a in self._by_name.get(name, ()) if a.lineno < line]
        return max(candidates, key=lambda a: a.lineno) if candidates else None


def receiver_methods(call: ast.Call, assignments: AssignmentIndex) -> list[str]:
    """Names of the methods/attributes that produced the object a method is called on.

    For ``df.filter(x).limit(5).collect()`` this returns ``["limit", "filter"]``.
    Simple variables are followed through ``assignments``, so

        small = df.limit(5)
        small.collect()

    also returns ``["limit"]`` for the ``collect`` call.
    """
    if not isinstance(call.func, ast.Attribute):
        return []
    return _chain(call.func.value, assignments, call.lineno, depth=0)


def _chain(node: ast.expr, assignments: AssignmentIndex, line: int, depth: int) -> list[str]:
    names: list[str] = []
    current: ast.expr = node
    while True:
        if isinstance(current, ast.Call):
            current = current.func
        elif isinstance(current, ast.Attribute):
            names.append(current.attr)
            current = current.value
        elif isinstance(current, ast.Subscript):
            current = current.value
        elif isinstance(current, ast.Name) and depth < _MAX_RESOLVE_DEPTH:
            assignment = assignments.latest_before(current.id, line)
            if assignment is not None:
                names.extend(_chain(assignment.value, assignments, assignment.lineno, depth + 1))
            return names
        else:
            return names


def attribute_name_position(attr: ast.Attribute) -> tuple[int, int]:
    """Position ``(line, byte_col)`` where the attribute *name* starts.

    ``line`` is 1-based; ``byte_col`` is a 0-based UTF-8 byte offset, as used by ``ast``.
    Convert it with :meth:`SourceFile.char_column` before reporting.

    For ``df.collect()`` this points at ``collect`` rather than at ``df``, which is what a
    user expects to see highlighted, also when the call is on its own line in a long chain.
    """
    line = attr.end_lineno if attr.end_lineno is not None else attr.lineno
    end_col = attr.end_col_offset if attr.end_col_offset is not None else attr.col_offset
    return line, end_col - len(attr.attr.encode("utf-8"))

"""Helpers for inspecting Python ASTs. Shared by every rule that checks Python code."""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Collection, Iterator
from typing import NamedTuple

from pipeline_lint.models import SourceKind

# Guards against pathological assignment chains (a = b; b = c; ...).
_MAX_RESOLVE_DEPTH = 10

# Modules whose presence marks a file as Spark code.
SPARK_MODULES = ("pyspark", "databricks.connect")


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


def is_spark_code(tree: ast.Module, kind: SourceKind) -> bool:
    """True for Databricks notebooks (which get a ready-made ``spark`` session and usually
    import nothing) and for files that import PySpark or Databricks Connect."""
    if kind == "databricks_notebook":
        return True
    return any(imports_module(tree, module) for module in SPARK_MODULES)


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


def string_arg(call: ast.Call, index: int = 0, keyword: str | None = None) -> str | None:
    """The value of a string-literal argument, by position or keyword, or None."""
    node: ast.expr | None = None
    if index < len(call.args):
        node = call.args[index]
    elif keyword is not None:
        node = next((kw.value for kw in call.keywords if kw.arg == keyword), None)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def insert_into_overwrite(call: ast.Call) -> bool:
    """True for ``insertInto(t, True)`` or ``insertInto(t, overwrite=True)``."""
    candidates = call.args[1:2] + [kw.value for kw in call.keywords if kw.arg == "overwrite"]
    return any(isinstance(node, ast.Constant) and node.value is True for node in candidates)


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


class ChainLink(NamedTuple):
    """One step in a method chain: the attribute name and, if it was called, the call node."""

    name: str
    call: ast.Call | None


def receiver_chain(call: ast.Call, assignments: AssignmentIndex) -> list[ChainLink]:
    """The steps that produced the object a method is called on, innermost last.

    For ``df.write.mode("append")`` and the ``mode`` call this returns ``[write]``.
    For ``df.filter(x).limit(5).collect()`` it returns ``[limit(5), filter(x)]``.
    Simple variables are followed through ``assignments``, so

        small = df.limit(5)
        small.collect()

    also sees the ``limit`` step.
    """
    if not isinstance(call.func, ast.Attribute):
        return []
    return _chain(call.func.value, assignments, call.lineno, depth=0)


def receiver_methods(call: ast.Call, assignments: AssignmentIndex) -> list[str]:
    """Just the names from :func:`receiver_chain`."""
    return [link.name for link in receiver_chain(call, assignments)]


def _chain(node: ast.expr, assignments: AssignmentIndex, line: int, depth: int) -> list[ChainLink]:
    links: list[ChainLink] = []
    pending_call: ast.Call | None = None
    current: ast.expr = node
    while True:
        if isinstance(current, ast.Call):
            pending_call = current
            current = current.func
        elif isinstance(current, ast.Attribute):
            links.append(ChainLink(current.attr, pending_call))
            pending_call = None
            current = current.value
        elif isinstance(current, ast.Subscript):
            pending_call = None
            current = current.value
        elif isinstance(current, ast.Name) and depth < _MAX_RESOLVE_DEPTH:
            assignment = assignments.latest_before(current.id, line)
            if assignment is not None:
                links.extend(_chain(assignment.value, assignments, assignment.lineno, depth + 1))
            return links
        else:
            return links


def parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    """Map every node to its parent, so rules can look at what happens *after* a call."""
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def chained_calls(call: ast.Call, parents: dict[ast.AST, ast.AST]) -> Iterator[ChainLink]:
    """Steps chained *after* ``call``.

    For ``df.write.mode("append").format("delta").saveAsTable("t")`` and the ``mode`` call this
    yields ``format("delta")`` then ``saveAsTable("t")``.
    """
    node: ast.AST = call
    while True:
        attr = parents.get(node)
        if not (isinstance(attr, ast.Attribute) and attr.value is node):
            return
        outer = parents.get(attr)
        if isinstance(outer, ast.Call) and outer.func is attr:
            yield ChainLink(attr.attr, outer)
            node = outer
        else:
            yield ChainLink(attr.attr, None)
            node = attr


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

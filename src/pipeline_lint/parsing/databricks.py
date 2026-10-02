"""Databricks notebooks exported in source format (``.py`` files)."""

from __future__ import annotations

from collections.abc import Iterator

NOTEBOOK_HEADER = "# Databricks notebook source"
MAGIC_PREFIX = "# MAGIC"


def is_databricks_notebook(text: str) -> bool:
    """Return True if the first non-empty line is the Databricks source-format header."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped == NOTEBOOK_HEADER
    return False


def iter_magic_sql_cells(text: str) -> Iterator[tuple[str, int]]:
    """Yield ``(sql_text, first_line)`` for every ``%sql`` cell in a Databricks notebook.

    In source format a SQL cell looks like::

        # MAGIC %sql
        # MAGIC INSERT INTO t
        # MAGIC SELECT ...

    The returned text keeps one line per notebook line (the ``%sql`` line itself becomes the
    first, usually empty, line), so line numbers map back to the notebook file exactly.
    """
    lines = text.split("\n")
    index = 0
    while index < len(lines):
        body = _magic_body(lines[index])
        if body is None or not body.strip().lower().startswith("%sql"):
            index += 1
            continue

        first_line = index + 1
        sql_lines = [body.strip()[len("%sql") :]]
        index += 1
        while index < len(lines) and (next_body := _magic_body(lines[index])) is not None:
            sql_lines.append(next_body)
            index += 1
        yield "\n".join(sql_lines), first_line


def _magic_body(line: str) -> str | None:
    """The content after ``# MAGIC``, or None if the line is not a magic line."""
    stripped = line.lstrip()
    if not stripped.startswith(MAGIC_PREFIX):
        return None
    body = stripped[len(MAGIC_PREFIX) :]
    return body[1:] if body.startswith(" ") else body

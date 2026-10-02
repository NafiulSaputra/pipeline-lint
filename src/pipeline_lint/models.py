"""Core data model shared by parsers, rules, the engine and reporters."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from sqlglot import exp

SourceKind = Literal["sql", "python", "databricks_notebook"]

# Where a SQL statement came from: a .sql file, a spark.sql("...") call, or a %sql notebook cell.
SqlOrigin = Literal["sql_file", "spark_sql", "notebook_magic"]


class Severity(StrEnum):
    """How serious a violation is. Both levels fail the run by default."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, order=True)
class Violation:
    """A single rule violation at a specific location.

    Field order defines sort order: violations are reported by file, then line, then column.
    Line and column are 1-based, matching what editors and SARIF expect.
    """

    path: Path
    line: int
    column: int
    rule_id: str
    severity: Severity
    message: str


@dataclass(frozen=True)
class SqlStatement:
    """One parsed SQL statement, with its position in the original file."""

    expression: exp.Expression
    line: int
    column: int
    origin: SqlOrigin


@dataclass(frozen=True, order=True)
class ParseNotice:
    """Part of a file that could not be parsed and was therefore not checked.

    Notices are shown to the user but never fail the run: the linter cannot claim a
    violation in code it could not read.
    """

    path: Path
    line: int
    message: str


@dataclass(frozen=True)
class SourceFile:
    """A file loaded from disk, classified and parsed."""

    path: Path
    text: str
    kind: SourceKind
    python_ast: ast.Module | None = None
    sql_statements: tuple[SqlStatement, ...] = ()
    notices: tuple[ParseNotice, ...] = ()

    @property
    def is_python(self) -> bool:
        return self.kind in ("python", "databricks_notebook")

    @cached_property
    def lines(self) -> list[str]:
        """Source lines, indexed so that ``lines[n - 1]`` is line ``n``."""
        return self.text.split("\n")

    def find_text(self, needle: str, start: tuple[int, int] = (1, 1)) -> tuple[int, int] | None:
        """1-based ``(line, column)`` of the first ``needle`` at or after ``start``, or None.

        Used to point SQL violations at the exact literal: sqlglot does not keep source
        positions for every node, but the literal's text appears verbatim in the file.
        """
        start_line, start_column = start
        for index in range(max(start_line, 1) - 1, len(self.lines)):
            offset = start_column - 1 if index == start_line - 1 else 0
            found = self.lines[index].find(needle, max(offset, 0))
            if found != -1:
                return index + 1, found + 1
        return None

    def char_column(self, line: int, byte_offset: int) -> int:
        """Convert a 0-based UTF-8 byte offset (as used by ``ast``) to a 1-based character column.

        ``ast`` reports offsets in bytes, so a non-ASCII character earlier on the line would
        otherwise shift every reported column to the right.
        """
        if not 1 <= line <= len(self.lines):
            return byte_offset + 1
        prefix = self.lines[line - 1].encode("utf-8")[:byte_offset]
        return len(prefix.decode("utf-8", errors="ignore")) + 1


@dataclass(frozen=True)
class SkippedFile:
    """A file that could not be checked at all, with a human-readable reason."""

    path: Path
    reason: str

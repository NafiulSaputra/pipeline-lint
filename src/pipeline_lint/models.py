"""Core data model shared by parsers, rules, the engine and reporters."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import Literal

SourceKind = Literal["sql", "python", "databricks_notebook"]


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
class SourceFile:
    """A file loaded from disk, classified and (for Python) parsed."""

    path: Path
    text: str
    kind: SourceKind
    python_ast: ast.Module | None = None

    @property
    def is_python(self) -> bool:
        return self.kind in ("python", "databricks_notebook")

    @cached_property
    def lines(self) -> list[str]:
        """Source lines, indexed so that ``lines[n - 1]`` is line ``n``."""
        return self.text.split("\n")

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
    """A file that could not be checked, with a human-readable reason."""

    path: Path
    reason: str

"""Output formats for lint results."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path


class OutputFormat(StrEnum):
    TEXT = "text"
    JSON = "json"
    SARIF = "sarif"


def relative_posix(path: Path) -> str:
    """``path`` relative to the working directory, with forward slashes on every OS.

    Machine-readable reports must not depend on the platform they were produced on: a CI
    job on Windows and one on Linux should emit the same paths.
    """
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()

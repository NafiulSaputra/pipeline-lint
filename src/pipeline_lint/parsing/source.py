"""Load a file from disk, classify it and parse it."""

from __future__ import annotations

import ast
from pathlib import Path

from pipeline_lint.errors import SourceError
from pipeline_lint.models import SourceFile
from pipeline_lint.parsing.databricks import is_databricks_notebook


def load_source(path: Path) -> SourceFile:
    """Read and parse ``path``.

    Raises:
        SourceError: the file cannot be read, is not UTF-8, or is not valid Python.
    """
    try:
        # utf-8-sig transparently drops the byte-order mark some Windows editors add.
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SourceError(path, "file is not valid UTF-8") from exc
    except OSError as exc:
        raise SourceError(path, f"cannot read file ({exc.strerror})") from exc

    suffix = path.suffix.lower()
    if suffix == ".sql":
        return SourceFile(path=path, text=text, kind="sql")

    if suffix == ".py":
        kind = "databricks_notebook" if is_databricks_notebook(text) else "python"
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            location = f" at line {exc.lineno}" if exc.lineno else ""
            raise SourceError(path, f"Python syntax error{location}: {exc.msg}") from exc
        except ValueError as exc:  # e.g. null bytes in the source
            raise SourceError(path, f"cannot parse Python source ({exc})") from exc
        return SourceFile(path=path, text=text, kind=kind, python_ast=tree)

    raise SourceError(path, f"unsupported file type '{suffix}'")

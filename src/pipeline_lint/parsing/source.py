"""Load a file from disk, classify it and parse it."""

from __future__ import annotations

import ast
from pathlib import Path

from pipeline_lint.errors import SourceError
from pipeline_lint.models import ParseNotice, SourceFile, SqlOrigin, SqlStatement
from pipeline_lint.parsing.databricks import is_databricks_notebook, iter_magic_sql_cells
from pipeline_lint.parsing.embedded_sql import iter_embedded_sql
from pipeline_lint.parsing.python import is_spark_code
from pipeline_lint.parsing.sql import DEFAULT_DIALECT, parse_sql


def load_source(path: Path, *, sql_dialect: str = DEFAULT_DIALECT) -> SourceFile:
    """Read and parse ``path``.

    SQL is collected from ``.sql`` files and, in Spark Python files, from ``spark.sql("...")``
    calls and ``%sql`` notebook cells. All statements end up in ``SourceFile.sql_statements``,
    ordered by line, so SQL rules see one consistent sequence whatever the file type.

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
        statements, notices = parse_sql(
            text, path=path, first_line=1, origin="sql_file", dialect=sql_dialect
        )
        return SourceFile(
            path=path,
            text=text,
            kind="sql",
            sql_statements=tuple(statements),
            notices=tuple(notices),
        )

    if suffix == ".py":
        kind = "databricks_notebook" if is_databricks_notebook(text) else "python"
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            location = f" at line {exc.lineno}" if exc.lineno else ""
            raise SourceError(path, f"Python syntax error{location}: {exc.msg}") from exc
        except ValueError as exc:  # e.g. null bytes in the source
            raise SourceError(path, f"cannot parse Python source ({exc})") from exc

        fragments: list[tuple[str, int, SqlOrigin]] = []
        if is_spark_code(tree, kind):
            fragments += [(sql, line, "spark_sql") for sql, line in iter_embedded_sql(tree)]
            if kind == "databricks_notebook":
                fragments += [
                    (sql, line, "notebook_magic") for sql, line in iter_magic_sql_cells(text)
                ]

        statements: list[SqlStatement] = []
        notices: list[ParseNotice] = []
        for sql, first_line, origin in fragments:
            found, problems = parse_sql(
                sql, path=path, first_line=first_line, origin=origin, dialect=sql_dialect
            )
            statements += found
            notices += problems

        return SourceFile(
            path=path,
            text=text,
            kind=kind,
            python_ast=tree,
            sql_statements=tuple(sorted(statements, key=lambda s: (s.line, s.column))),
            notices=tuple(sorted(notices)),
        )

    raise SourceError(path, f"unsupported file type '{suffix}'")

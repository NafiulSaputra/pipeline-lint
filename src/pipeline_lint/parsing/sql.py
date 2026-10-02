"""SQL parsing with sqlglot: statement splitting, templating masks and table names."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.tokens import Token, TokenType

from pipeline_lint.models import ParseNotice, SqlOrigin, SqlStatement

DEFAULT_DIALECT = "spark"

# Jinja ({{ ds }}, {% if %}, {# comment #}) and Spark/Databricks variable substitution (${var}).
# SQL in Airflow and dbt projects is usually templated, and sqlglot cannot parse templates.
_TEMPLATE_PATTERN = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}|\$\{[^}\n]*\}", re.DOTALL)
TEMPLATE_PLACEHOLDER = "__template__"

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
_TRUNCATE_COMMAND = re.compile(r"^\s*(?:TABLE\s+)?([\w.`\"\[\]]+)", re.IGNORECASE)


def mask_templating(sql: str) -> str:
    """Replace template expressions with a parseable placeholder, keeping line numbers intact.

    ``{{ expr }}`` and ``${var}`` become an identifier-like placeholder (valid both as a value and
    inside quotes). ``{% tag %}`` and ``{# comment #}`` are removed. Newlines inside a template
    are preserved so every reported line number still matches the original file.
    """

    def replace(match: re.Match[str]) -> str:
        text = match.group(0)
        newlines = "\n" * text.count("\n")
        if text.startswith(("{%", "{#")):
            return newlines
        return TEMPLATE_PLACEHOLDER + newlines

    return _TEMPLATE_PATTERN.sub(replace, sql)


def parse_sql(
    sql: str,
    *,
    path: Path,
    first_line: int,
    origin: SqlOrigin,
    dialect: str = DEFAULT_DIALECT,
) -> tuple[list[SqlStatement], list[ParseNotice]]:
    """Split ``sql`` into statements and parse each one separately.

    Parsing statement by statement means one unsupported statement does not hide problems in
    the rest of the file. ``first_line`` is the file line where ``sql`` starts, so statements
    extracted from Python strings or notebook cells report their real position in the file.
    """
    text = mask_templating(sql)
    try:
        tokens = sqlglot.tokenize(text, read=dialect)
    except SqlglotError as exc:
        notice = ParseNotice(path, first_line, f"SQL skipped, cannot tokenize: {_describe(exc)}")
        return [], [notice]

    statements: list[SqlStatement] = []
    notices: list[ParseNotice] = []
    for chunk in _split_statements(tokens):
        start, end = chunk[0].start, chunk[-1].end
        line = first_line + chunk[0].line - 1
        try:
            expression = sqlglot.parse_one(text[start : end + 1], read=dialect)
        except SqlglotError as exc:
            notices.append(
                ParseNotice(path, line, f"SQL statement skipped, cannot parse: {_describe(exc)}")
            )
            continue
        if expression is None:
            continue
        # Exact columns are only meaningful for .sql files; extracted SQL is shifted by the
        # surrounding Python string or "# MAGIC" prefix, so it reports column 1.
        column = start - text.rfind("\n", 0, start) if origin == "sql_file" else 1
        statements.append(SqlStatement(expression, line=line, column=column, origin=origin))
    return statements, notices


def _split_statements(tokens: list[Token]) -> Iterator[list[Token]]:
    chunk: list[Token] = []
    for token in tokens:
        if token.token_type == TokenType.SEMICOLON:
            if chunk:
                yield chunk
            chunk = []
        else:
            chunk.append(token)
    if chunk:
        yield chunk


def _describe(exc: SqlglotError) -> str:
    errors = getattr(exc, "errors", None)
    message = errors[0].get("description") if errors else None
    text = _ANSI_ESCAPE.sub("", str(message or exc)).strip()
    return text.splitlines()[0] if text else type(exc).__name__


@dataclass(frozen=True)
class TableName:
    """A case-insensitive, possibly qualified table name such as ``catalog.schema.table``."""

    parts: tuple[str, ...]

    @classmethod
    def from_table(cls, table: exp.Table) -> TableName | None:
        parts = tuple(p.lower() for p in (table.catalog, table.db, table.name) if p)
        return cls(parts) if parts else None

    @classmethod
    def from_string(cls, name: str) -> TableName | None:
        parts = tuple(
            p.strip().strip('`"[]').lower() for p in name.split(".") if p.strip().strip('`"[]')
        )
        return cls(parts) if parts else None

    def matches(self, other: TableName) -> bool:
        """True if both names can refer to the same table.

        ``orders`` matches ``sales.orders``: an unqualified name resolves against the current
        schema, which a linter cannot know, so we assume it is the same table. That choice
        avoids false positives at the cost of occasionally missing a real issue.
        """
        shorter, longer = sorted((self.parts, other.parts), key=len)
        return longer[len(longer) - len(shorter) :] == shorter

    def __str__(self) -> str:
        return ".".join(self.parts)


def insert_target(insert: exp.Insert) -> exp.Table | None:
    """The table an INSERT writes to (``INSERT INTO t (a, b)`` wraps ``t`` in a Schema node)."""
    target = insert.this
    if isinstance(target, exp.Schema):
        target = target.this
    return target if isinstance(target, exp.Table) else None


def cleared_tables(expression: exp.Expression) -> Iterator[TableName]:
    """Tables that a DELETE or TRUNCATE statement clears (fully or partly)."""
    if isinstance(expression, exp.Delete) and isinstance(expression.this, exp.Table):
        name = TableName.from_table(expression.this)
        if name:
            yield name
        return

    truncate_cls = getattr(exp, "TruncateTable", None)  # added in newer sqlglot versions
    if truncate_cls is not None and isinstance(expression, truncate_cls):
        for table in expression.expressions:
            if isinstance(table, exp.Table) and (name := TableName.from_table(table)):
                yield name
        return

    # Older sqlglot versions parse TRUNCATE as a generic command.
    if isinstance(expression, exp.Command) and str(expression.this).upper() == "TRUNCATE":
        match = _TRUNCATE_COMMAND.match(expression.text("expression"))
        if match and (name := TableName.from_string(match.group(1))):
            yield name

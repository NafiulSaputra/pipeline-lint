"""Configuration from ``[tool.pipeline-lint]`` in ``pyproject.toml``, plus CLI overrides."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import sqlglot

from pipeline_lint.errors import ConfigError
from pipeline_lint.models import Severity
from pipeline_lint.parsing.sql import DEFAULT_DIALECT

SECTION = "pipeline-lint"
KNOWN_KEYS = ("select", "ignore", "exclude", "sql-dialect", "fail-on")

# "DE" selects every rule, "DE00" selects DE001-DE009, "DE001" selects one rule.
RULE_SELECTOR = re.compile(r"DE\d{0,3}")


@dataclass(frozen=True)
class Config:
    select: tuple[str, ...] | None = None  # None means "all rules"
    ignore: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    sql_dialect: str = DEFAULT_DIALECT
    fail_on: Severity = Severity.WARNING
    # Directory of the pyproject.toml the settings came from. Exclude patterns are matched
    # relative to it, so they behave the same whichever directory the CLI is run from.
    root: Path | None = None
    source: Path | None = None


def find_pyproject(start: Path) -> Path | None:
    """The nearest ``pyproject.toml`` in ``start`` or any parent directory."""
    start = start.resolve()
    for directory in (start, *start.parents):
        candidate = directory / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None


def load_config(path: Path | None = None, *, start: Path | None = None) -> Config:
    """Load settings from ``path``, or from the nearest pyproject.toml above ``start``.

    A pyproject.toml without a ``[tool.pipeline-lint]`` section simply means defaults.

    Raises:
        ConfigError: the file is missing (when given explicitly), unreadable, or invalid.
    """
    if path is None:
        path = find_pyproject(start or Path.cwd())
        if path is None:
            return Config()
    elif not path.is_file():
        raise ConfigError(f"config file not found: {path}")

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc

    tool = data.get("tool", {})
    section = tool.get(SECTION, {}) if isinstance(tool, dict) else {}
    if not isinstance(section, dict):
        raise ConfigError(f"{path}: [tool.{SECTION}] must be a table")
    return parse_section(section, source=path)


def parse_section(section: dict[str, Any], *, source: Path) -> Config:
    unknown = sorted(set(section) - set(KNOWN_KEYS))
    if unknown:
        raise ConfigError(
            f"{source}: unknown option(s) in [tool.{SECTION}]: {', '.join(unknown)}. "
            f"Valid options: {', '.join(KNOWN_KEYS)}"
        )

    select = section.get("select")
    return Config(
        select=None if select is None else parse_selectors(_strings(select, "select", source)),
        ignore=parse_selectors(_strings(section.get("ignore", []), "ignore", source)),
        exclude=tuple(_strings(section.get("exclude", []), "exclude", source)),
        sql_dialect=validate_dialect(
            _string(section.get("sql-dialect", DEFAULT_DIALECT), "sql-dialect", source)
        ),
        fail_on=parse_fail_on(_string(section.get("fail-on", "warning"), "fail-on", source)),
        root=source.parent.resolve(),
        source=source,
    )


def with_overrides(
    config: Config,
    *,
    select: Sequence[str] | None = None,
    ignore: Sequence[str] | None = None,
    sql_dialect: str | None = None,
    fail_on: Severity | None = None,
) -> Config:
    """Apply command-line options: ``select`` replaces the config, ``ignore`` adds to it."""
    updated = config
    if select is not None:
        updated = replace(updated, select=parse_selectors(select))
    if ignore:
        updated = replace(updated, ignore=updated.ignore + parse_selectors(ignore))
    if sql_dialect is not None:
        updated = replace(updated, sql_dialect=validate_dialect(sql_dialect))
    if fail_on is not None:
        updated = replace(updated, fail_on=fail_on)
    return updated


def parse_selectors(values: Sequence[str]) -> tuple[str, ...]:
    selectors = tuple(value.strip().upper() for value in values if value.strip())
    for selector in selectors:
        if not RULE_SELECTOR.fullmatch(selector):
            raise ConfigError(
                f"invalid rule selector {selector!r}: use a rule ID like 'DE001' or a prefix "
                "like 'DE'"
            )
    return selectors


def parse_fail_on(value: str) -> Severity:
    try:
        return Severity(value.lower())
    except ValueError:
        raise ConfigError(f"invalid fail-on {value!r}: use 'warning' or 'error'") from None


def validate_dialect(name: str) -> str:
    try:
        sqlglot.Dialect.get_or_raise(name)
    except ValueError as exc:
        raise ConfigError(f"unknown SQL dialect {name!r}: {exc}") from None
    return name


def _strings(value: Any, key: str, source: Path) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f'{source}: "{key}" must be a list of strings, e.g. ["DE001"]')
    return value


def _string(value: Any, key: str, source: Path) -> str:
    if not isinstance(value, str):
        raise ConfigError(f'{source}: "{key}" must be a string')
    return value

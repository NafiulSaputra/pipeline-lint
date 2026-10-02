"""Command-line interface.

Exit codes:
    0  no violations at or above the --fail-on severity
    1  at least one violation at or above the --fail-on severity
    2  usage, configuration or internal error
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from pipeline_lint import __version__
from pipeline_lint.config import load_config, with_overrides
from pipeline_lint.engine import LintResult, lint_paths
from pipeline_lint.errors import ConfigError, RuleCrashError
from pipeline_lint.models import Severity
from pipeline_lint.reporters import OutputFormat
from pipeline_lint.reporters.json import render_json
from pipeline_lint.reporters.sarif import render_sarif
from pipeline_lint.reporters.text import SEVERITY_STYLES, render_text
from pipeline_lint.rules import REGISTRY, Rule, select_rules

EXIT_OK = 0
EXIT_VIOLATIONS = 1
EXIT_ERROR = 2

ISSUES_URL = "https://github.com/NafiulSaputra/pipeline-lint/issues"

app = typer.Typer(
    name="pipeline-lint",
    help="Catch rerun-safety and data-correctness issues in SQL, PySpark and Airflow code.",
    no_args_is_help=True,
    add_completion=False,
)


def _make_consoles() -> tuple[Console, Console]:
    # soft_wrap keeps each violation on one line, so output stays greppable.
    return Console(soft_wrap=True, highlight=False), Console(
        stderr=True, soft_wrap=True, highlight=False
    )


def _fail(err_console: Console, message: str) -> typer.Exit:
    err_console.print(Text.assemble(("error: ", "bold red"), message))
    return typer.Exit(EXIT_ERROR)


def _split(value: str | None) -> list[str] | None:
    return None if value is None else [part for part in value.split(",") if part.strip()]


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"pipeline-lint {__version__}")
        raise typer.Exit(EXIT_OK)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Catch rerun-safety and data-correctness issues in SQL, PySpark and Airflow code."""


@app.command()
def check(
    paths: Annotated[
        list[Path] | None,
        typer.Argument(
            help="Files or directories to check. Defaults to the current directory.",
            exists=True,
            show_default=False,
        ),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Report format.", case_sensitive=False),
    ] = OutputFormat.TEXT,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Write the report to this file instead of stdout.",
            dir_okay=False,
        ),
    ] = None,
    select: Annotated[
        str | None,
        typer.Option(help="Comma-separated rule IDs or prefixes to run (replaces the config)."),
    ] = None,
    ignore: Annotated[
        str | None,
        typer.Option(help="Comma-separated rule IDs or prefixes to skip (added to the config)."),
    ] = None,
    fail_on: Annotated[
        Severity | None,
        typer.Option(
            "--fail-on",
            help="Lowest severity that makes the command exit with 1. [default: warning]",
            case_sensitive=False,
            show_default=False,
        ),
    ] = None,
    sql_dialect: Annotated[
        str | None,
        typer.Option(
            "--sql-dialect",
            help="sqlglot dialect used to parse SQL, e.g. spark, databricks, bigquery. "
            "[default: spark]",
            show_default=False,
        ),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            help="pyproject.toml to read [tool.pipeline-lint] from. "
            "Default: the nearest one above the current directory.",
            exists=True,
            dir_okay=False,
        ),
    ] = None,
) -> None:
    """Check files for pipeline issues."""
    console, err_console = _make_consoles()

    try:
        settings = with_overrides(
            load_config(config),
            select=_split(select),
            ignore=_split(ignore),
            sql_dialect=sql_dialect,
            fail_on=fail_on,
        )
    except ConfigError as exc:
        raise _fail(err_console, str(exc)) from exc

    rules = select_rules(REGISTRY.rules(), settings.select, settings.ignore)
    try:
        result = lint_paths(
            paths or [Path(".")],
            rules=rules,
            exclude=settings.exclude,
            exclude_root=settings.root,
            sql_dialect=settings.sql_dialect,
        )
    except RuleCrashError as exc:
        err_console.print(f"internal error: {exc}", style="bold red", markup=False)
        err_console.print(f"This is a bug in pipeline-lint. Please report it: {ISSUES_URL}")
        raise typer.Exit(EXIT_ERROR) from exc

    try:
        _write_report(result, rules, output_format, output, console, err_console)
    except OSError as exc:
        raise _fail(err_console, f"cannot write report to {output}: {exc}") from exc

    threshold = settings.fail_on.rank
    failed = any(v.severity.rank >= threshold for v in result.violations)
    raise typer.Exit(EXIT_VIOLATIONS if failed else EXIT_OK)


def _write_report(
    result: LintResult,
    rules: list[Rule],
    output_format: OutputFormat,
    output: Path | None,
    console: Console,
    err_console: Console,
) -> None:
    if output_format is OutputFormat.TEXT:
        if output is None:
            render_text(result, console, err_console)
            return
        with output.open("w", encoding="utf-8") as handle:
            render_text(result, Console(file=handle, soft_wrap=True, highlight=False), err_console)
        return

    if output_format is OutputFormat.JSON:
        report = render_json(result)
    else:
        report = render_sarif(result, rules)
    if output is None:
        typer.echo(report)
    else:
        output.write_text(report + "\n", encoding="utf-8")


@app.command("rules")
def list_rules() -> None:
    """List all available rules."""
    console, _ = _make_consoles()
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name", no_wrap=True)
    table.add_column("Severity", no_wrap=True)
    table.add_column("Summary")
    for rule in REGISTRY.rules():
        table.add_row(
            rule.id,
            rule.name,
            Text(str(rule.severity), style=SEVERITY_STYLES[rule.severity]),
            Text(rule.summary),
        )
    console.print(table)

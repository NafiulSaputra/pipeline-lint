"""Command-line interface.

Exit codes:
    0  no violations
    1  at least one violation
    2  usage error or internal error
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from pipeline_lint import __version__
from pipeline_lint.engine import lint_paths
from pipeline_lint.errors import RuleCrashError
from pipeline_lint.reporters.text import SEVERITY_STYLES, render_text
from pipeline_lint.rules import REGISTRY

EXIT_OK = 0
EXIT_VIOLATIONS = 1
EXIT_ERROR = 2

ISSUES_URL = "https://github.com/<NafiulSaputra>/pipeline-lint/issues"

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
) -> None:
    """Check files for pipeline issues."""
    console, err_console = _make_consoles()
    targets = paths or [Path(".")]

    try:
        result = lint_paths(targets)
    except RuleCrashError as exc:
        err_console.print(f"internal error: {exc}", style="bold red", markup=False)
        err_console.print(f"This is a bug in pipeline-lint. Please report it: {ISSUES_URL}")
        raise typer.Exit(EXIT_ERROR) from exc

    render_text(result, console, err_console)
    raise typer.Exit(EXIT_VIOLATIONS if result.violations else EXIT_OK)


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

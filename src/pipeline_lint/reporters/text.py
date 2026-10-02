"""Human-readable terminal output."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.text import Text

from pipeline_lint.engine import LintResult
from pipeline_lint.models import Severity

SEVERITY_STYLES = {
    Severity.ERROR: "bold red",
    Severity.WARNING: "yellow",
}


def render_text(result: LintResult, console: Console, err_console: Console) -> None:
    """Print violations grouped by file, followed by a one-line summary.

    Everything is built with ``Text`` objects rather than markup strings, so messages that
    contain square brackets (``row[0]``) are never interpreted as Rich styling.
    """
    for skipped in result.skipped:
        err_console.print(
            Text.assemble(("warning: ", "yellow"), f"skipped {skipped.path}: {skipped.reason}")
        )

    for notice in result.notices:
        err_console.print(
            Text.assemble(("warning: ", "yellow"), f"{notice.path}:{notice.line}: {notice.message}")
        )

    current_path: Path | None = None
    for violation in result.violations:
        if violation.path != current_path:
            if current_path is not None:
                console.print()
            console.print(Text(str(violation.path), style="bold underline"))
            current_path = violation.path
        console.print(
            Text.assemble(
                f"  {violation.line}:{violation.column}".ljust(11),
                (f"{violation.severity:<9}", SEVERITY_STYLES[violation.severity]),
                (f"{violation.rule_id}  ", "cyan"),
                violation.message,
            )
        )

    if result.violations:
        console.print()
    console.print(_summary(result))


def _summary(result: LintResult) -> Text:
    if not result.violations:
        return Text(
            f"All checks passed ({_plural(result.files_checked, 'file')} checked).",
            style="green",
        )
    return Text(
        f"Found {_plural(len(result.violations), 'violation')} "
        f"({_plural(result.error_count, 'error')}, {_plural(result.warning_count, 'warning')}) "
        f"in {_plural(result.files_with_violations, 'file')}.",
        style="bold",
    )


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"

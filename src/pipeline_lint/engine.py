"""Run rules over files and collect the results."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pipeline_lint.discovery import discover_files
from pipeline_lint.errors import RuleCrashError, SourceError
from pipeline_lint.models import ParseNotice, Severity, SkippedFile, SourceFile, Violation
from pipeline_lint.noqa import apply_noqa
from pipeline_lint.parsing import load_source
from pipeline_lint.parsing.sql import DEFAULT_DIALECT
from pipeline_lint.rules import REGISTRY, Rule


@dataclass(frozen=True)
class LintResult:
    """Everything a reporter needs to describe one run."""

    violations: list[Violation]
    files_checked: int
    skipped: list[SkippedFile] = field(default_factory=list)
    notices: list[ParseNotice] = field(default_factory=list)
    suppressed: int = 0  # violations hidden by noqa comments

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity is Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity is Severity.WARNING)

    @property
    def files_with_violations(self) -> int:
        return len({v.path for v in self.violations})


def lint_paths(
    paths: Iterable[Path],
    *,
    rules: Iterable[Rule] | None = None,
    exclude: Sequence[str] = (),
    exclude_root: Path | None = None,
    sql_dialect: str = DEFAULT_DIALECT,
) -> LintResult:
    """Lint every supported file under ``paths``.

    Files that cannot be read or parsed are reported in ``LintResult.skipped``, and SQL
    statements that cannot be parsed in ``LintResult.notices``, instead of stopping the run:
    one broken file should not hide problems in the other hundred.

    Raises:
        FileNotFoundError: a path in ``paths`` does not exist.
        RuleCrashError: a rule raised an unexpected exception.
    """
    active_rules = list(rules) if rules is not None else REGISTRY.rules()
    violations: list[Violation] = []
    skipped: list[SkippedFile] = []
    notices: list[ParseNotice] = []
    suppressed = 0
    files_checked = 0

    for path in discover_files(paths, exclude=exclude, root=exclude_root):
        try:
            source = load_source(path, sql_dialect=sql_dialect)
        except SourceError as exc:
            skipped.append(SkippedFile(path=path, reason=exc.reason))
            continue
        files_checked += 1
        notices.extend(source.notices)
        kept, hidden = apply_noqa(source, lint_source(source, active_rules))
        violations.extend(kept)
        suppressed += hidden

    return LintResult(
        violations=sorted(violations),
        files_checked=files_checked,
        skipped=skipped,
        notices=sorted(notices),
        suppressed=suppressed,
    )


def lint_source(source: SourceFile, rules: Iterable[Rule]) -> list[Violation]:
    """Run ``rules`` on one already-loaded source file."""
    found: list[Violation] = []
    for rule in rules:
        try:
            if source.is_python:
                found.extend(rule.check_python(source))
            if source.sql_statements:
                found.extend(rule.check_sql(source))
        except Exception as exc:
            # Fail loudly: silently skipping a crashed rule would report "all clear" for code
            # that was never actually checked.
            raise RuleCrashError(rule.id, source.path) from exc
    return found

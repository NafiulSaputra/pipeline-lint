"""Per-line suppression with ``# noqa: DE001`` (Python) or ``-- noqa: DE001`` (SQL)."""

from __future__ import annotations

import re
from collections.abc import Iterable

from pipeline_lint.models import SourceFile, Violation

# Codes are required: a blanket noqa without codes is ignored, so every suppression names
# what it hides. Other tools' codes may share the same comment, e.g. "noqa: E501, DE001".
NOQA_PATTERN = re.compile(
    r"(?:#|--)\s*noqa\s*:\s*(?P<codes>[A-Za-z]+\d+(?:[\s,]+[A-Za-z]+\d+)*)", re.IGNORECASE
)


def suppressed_codes(line: str) -> frozenset[str]:
    """Rule codes listed in the noqa comments of ``line``, upper-cased."""
    codes: set[str] = set()
    for match in NOQA_PATTERN.finditer(line):
        codes.update(code.upper() for code in re.split(r"[\s,]+", match["codes"]) if code)
    return frozenset(codes)


def apply_noqa(source: SourceFile, violations: Iterable[Violation]) -> tuple[list[Violation], int]:
    """Split violations into the ones to report and a count of suppressed ones."""
    kept: list[Violation] = []
    suppressed = 0
    cache: dict[int, frozenset[str]] = {}
    for violation in violations:
        line = violation.line
        if line not in cache:
            text = source.lines[line - 1] if 1 <= line <= len(source.lines) else ""
            cache[line] = suppressed_codes(text)
        if violation.rule_id in cache[line]:
            suppressed += 1
        else:
            kept.append(violation)
    return kept, suppressed

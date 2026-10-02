"""Data-driven tests: every fixture declares the violations it expects.

Layout: ``tests/fixtures/<RULE_ID>/bad_*.{py,sql}`` and ``good_*.{py,sql}``.
A bad fixture marks each offending line with ``# expect: DE005`` (``-- expect:`` in SQL).
A good fixture must produce no violations. Adding a test case means adding a file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline_lint.engine import lint_paths
from pipeline_lint.rules import REGISTRY, select_rules

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
EXPECT_PATTERN = re.compile(r"(?:#|--)\s*expect:\s*(?P<codes>DE\d{3}(?:\s*,\s*DE\d{3})*)")


def fixture_files() -> list[Path]:
    return sorted(p for p in FIXTURES_DIR.rglob("*") if p.suffix in {".py", ".sql"})


def expected_violations(path: Path) -> set[tuple[int, str]]:
    expected: set[tuple[int, str]] = set()
    lines = path.read_text(encoding="utf-8").split("\n")
    for lineno, line in enumerate(lines, start=1):
        match = EXPECT_PATTERN.search(line)
        if match:
            expected.update((lineno, code.strip()) for code in match["codes"].split(","))
    return expected


def test_fixtures_exist() -> None:
    assert fixture_files(), f"no fixtures found under {FIXTURES_DIR}"


@pytest.mark.parametrize(
    "path", fixture_files(), ids=lambda p: p.relative_to(FIXTURES_DIR).as_posix()
)
def test_fixture(path: Path) -> None:
    rule_id = path.parent.name
    rules = select_rules(REGISTRY.rules(), select=[rule_id])
    assert rules, f"fixture folder {rule_id!r} does not match any registered rule"

    expected = expected_violations(path)
    if path.name.startswith("bad_"):
        assert expected, "a bad_ fixture must mark at least one line with 'expect:'"
    elif path.name.startswith("good_"):
        assert not expected, "a good_ fixture must not contain 'expect:' markers"
    else:
        pytest.fail("fixture file names must start with 'bad_' or 'good_'")

    result = lint_paths([path], rules=rules)

    assert not result.skipped, f"fixture could not be parsed: {result.skipped}"
    actual = {(v.line, v.rule_id) for v in result.violations}
    assert actual == expected

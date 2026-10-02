from __future__ import annotations

from pathlib import Path

import pytest

from pipeline_lint.engine import LintResult, lint_paths
from pipeline_lint.noqa import suppressed_codes
from pipeline_lint.rules import REGISTRY


@pytest.mark.parametrize(
    ("line", "codes"),
    [
        ("rows = df.collect()  # noqa: DE005", {"DE005"}),
        ("INSERT INTO t SELECT 1;  -- noqa:DE001,DE004", {"DE001", "DE004"}),
        ("x = 1  # noqa: E501, DE003", {"E501", "DE003"}),
        ("x = 1  # NOQA: de005", {"DE005"}),
        ("x = 1  # noqa: DE001 legacy table, fixed in Q3", {"DE001"}),
        ("# MAGIC INSERT INTO t SELECT 1 -- noqa: DE001", {"DE001"}),
        ("x = 1  # noqa", set()),
        ("x = 1  # no qa: DE001", set()),
        ("x = 1", set()),
    ],
)
def test_suppressed_codes(line: str, codes: set[str]) -> None:
    assert suppressed_codes(line) == codes


def lint(tmp_path: Path, name: str, text: str) -> LintResult:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return lint_paths([path], rules=REGISTRY.rules())


def test_noqa_suppresses_only_the_named_rule(tmp_path: Path) -> None:
    code = (
        "from pyspark.sql import SparkSession\n"
        "rows = df.collect()  # noqa: DE005\n"
        "df.write.mode('append').saveAsTable('t')  # noqa: DE005\n"
    )
    result = lint(tmp_path, "job.py", code)
    assert [(v.line, v.rule_id) for v in result.violations] == [(3, "DE001")]
    assert result.suppressed == 1


def test_sql_noqa_on_statement_line(tmp_path: Path) -> None:
    sql = "INSERT INTO audit_log  -- noqa: DE001\nVALUES (1, 'loaded');\n"
    result = lint(tmp_path, "audit.sql", sql)
    assert result.violations == []
    assert result.suppressed == 1


def test_blanket_noqa_is_ignored(tmp_path: Path) -> None:
    result = lint(tmp_path, "audit.sql", "INSERT INTO audit_log VALUES (1);  -- noqa\n")
    assert [v.rule_id for v in result.violations] == ["DE001"]
    assert result.suppressed == 0

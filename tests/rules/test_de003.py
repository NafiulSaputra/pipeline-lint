"""Unit tests for DE003 edge cases that are clearer inline than as fixture files."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from pipeline_lint.engine import LintResult, lint_paths
from pipeline_lint.models import Severity
from pipeline_lint.rules import REGISTRY, select_rules
from pipeline_lint.rules.de003_hardcoded_date import is_hardcoded_date

SPARK_IMPORT = "from pyspark.sql import functions as F\n"


def lint(tmp_path: Path, code: str, filename: str) -> LintResult:
    path = tmp_path / filename
    path.write_text(textwrap.dedent(code), encoding="utf-8")
    rules = select_rules(REGISTRY.rules(), select=["DE003"])
    return lint_paths([path], rules=rules)


def lint_sql(tmp_path: Path, sql: str) -> LintResult:
    return lint(tmp_path, sql, "query.sql")


def lint_py(tmp_path: Path, code: str) -> LintResult:
    return lint(tmp_path, SPARK_IMPORT + code, "job.py")


def test_metadata() -> None:
    (rule,) = select_rules(REGISTRY.rules(), select=["DE003"])
    assert rule.name == "hardcoded-date"
    assert rule.severity is Severity.WARNING


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-01-01", True),
        ("2026-12-31 23:59", True),
        ("2026-01-01T08:30:00.123Z", True),
        ("2026-01-01 08:30:00+07:00", True),
        (" 2026-01-01 ", True),
        ("9999-12-31", False),
        ("9999-12-31 23:59:59", False),
        ("1900-01-01", False),
        ("2026-13-01", False),
        ("2026-01-32", False),
        ("2026-1-1", False),
        ("20260101", False),
        ("v2026-01-01", False),
        ("yyyy-MM-dd", False),
    ],
)
def test_is_hardcoded_date(text: str, expected: bool) -> None:
    assert is_hardcoded_date(text) is expected


# --- SQL ---------------------------------------------------------------------------------------


def test_points_at_the_literal(tmp_path: Path) -> None:
    sql = "SELECT id\nFROM t\nWHERE  d = '2026-01-01'"
    (violation,) = lint_sql(tmp_path, sql).violations
    assert (violation.line, violation.column) == (3, 13)
    assert "'2026-01-01'" in violation.message


def test_repeated_literal_is_reported_at_each_position(tmp_path: Path) -> None:
    sql = "SELECT id FROM t\nWHERE a = '2026-01-01'\n   OR b = '2026-01-01'"
    result = lint_sql(tmp_path, sql)
    assert [(v.line, v.column) for v in result.violations] == [(2, 12), (3, 12)]


@pytest.mark.parametrize(
    "condition",
    [
        "d = '2026-01-01'",
        "d <> '2026-01-01'",
        "d > '2026-01-01'",
        "d <= '2026-01-01'",
        "d BETWEEN '2026-01-01' AND '2026-01-31'",
        "d IN ('2026-01-01')",
        "d = DATE '2026-01-01'",
        "d >= to_date('2026-01-01')",
        "d = (SELECT MAX(x) FROM s WHERE y = '2026-01-01')",
    ],
)
def test_filter_comparisons_are_flagged(tmp_path: Path, condition: str) -> None:
    result = lint_sql(tmp_path, f"SELECT id FROM t WHERE {condition}")
    assert result.notices == []
    assert len(result.violations) >= 1


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id FROM t WHERE d = '{{ ds }}'",
        "SELECT id FROM t WHERE d = '${run_date}'",
        "SELECT id FROM t WHERE valid_to = '9999-12-31'",
        "SELECT id FROM t WHERE d >= date_sub(current_date(), 1)",
        "SELECT CASE WHEN d < '2020-01-01' THEN 1 END AS old FROM t",
        "SELECT id FROM t WHERE name = '2026-01-01-backup'",
        "SELECT id, '2026-01-01' AS release FROM t",
    ],
)
def test_not_flagged_in_sql(tmp_path: Path, sql: str) -> None:
    result = lint_sql(tmp_path, sql)
    assert result.notices == []
    assert result.violations == []


def test_join_condition_is_a_filter(tmp_path: Path) -> None:
    sql = "SELECT * FROM a JOIN b ON a.id = b.id AND b.d >= '2026-01-01'"
    assert len(lint_sql(tmp_path, sql).violations) == 1


def test_qualify_is_a_filter(tmp_path: Path) -> None:
    sql = (
        "SELECT id FROM t "
        "QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY ts) = 1 AND d > '2026-01-01'"
    )
    result = lint_sql(tmp_path, sql)
    assert result.notices == []
    assert len(result.violations) == 1


# --- PySpark -----------------------------------------------------------------------------------


def test_python_points_at_the_constant(tmp_path: Path) -> None:
    (violation,) = lint_py(tmp_path, "x = df.filter(F.col('d') >= '2026-01-01')\n").violations
    assert (violation.line, violation.column) == (2, 29)


def test_python_sql_expression_string(tmp_path: Path) -> None:
    code = "x = df.where(\"d >= '2026-01-01' AND valid_to = '9999-12-31'\")\n"
    (violation,) = lint_py(tmp_path, code).violations
    assert "'2026-01-01'" in violation.message


def test_python_sentinel_only_expression_string(tmp_path: Path) -> None:
    code = "x = df.where(\"valid_to = '9999-12-31'\")\n"
    assert lint_py(tmp_path, code).violations == []


@pytest.mark.parametrize(
    "call",
    [
        "date(2026, 1, 1)",
        "datetime(2026, 1, 1, 8, 30)",
        "datetime.datetime(2026, 1, 1)",
        "pendulum.datetime(2026, 1, 1, tz='UTC')",
    ],
)
def test_python_date_constructors(tmp_path: Path, call: str) -> None:
    (violation,) = lint_py(tmp_path, f"x = df.filter(F.col('d') > {call})\n").violations
    assert call.split("(")[0].split(".")[-1] in violation.message


def test_python_nested_between_reported_once(tmp_path: Path) -> None:
    code = "x = df.filter(F.col('d').between('2026-01-01', '2026-01-31'))\n"
    assert len(lint_py(tmp_path, code).violations) == 2


@pytest.mark.parametrize(
    "line",
    [
        "x = df.filter(F.col('d') == run_date)",
        "x = df.withColumn('v', F.lit('2026-01-01'))",
        "x = df.filter(F.col('d') > date(year, 1, 1))",
        "x = df.filter(F.col('d') == F.current_date())",
    ],
)
def test_python_not_flagged(tmp_path: Path, line: str) -> None:
    assert lint_py(tmp_path, line + "\n").violations == []


def test_ignored_outside_spark_code(tmp_path: Path) -> None:
    result = lint(tmp_path, "x = qs.filter(created__gte='2026-01-01')\n", "views.py")
    assert result.violations == []

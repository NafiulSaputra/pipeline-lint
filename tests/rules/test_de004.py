"""Unit tests for DE004 edge cases that are clearer inline than as fixture files."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from pipeline_lint.engine import LintResult, lint_paths
from pipeline_lint.models import Severity
from pipeline_lint.rules import REGISTRY, select_rules

SPARK_IMPORT = "from pyspark.sql import SparkSession\n"


def lint(tmp_path: Path, code: str, filename: str) -> LintResult:
    path = tmp_path / filename
    path.write_text(textwrap.dedent(code), encoding="utf-8")
    rules = select_rules(REGISTRY.rules(), select=["DE004"])
    return lint_paths([path], rules=rules)


def lint_sql(tmp_path: Path, sql: str) -> LintResult:
    return lint(tmp_path, sql, "query.sql")


def lint_py(tmp_path: Path, code: str) -> LintResult:
    return lint(tmp_path, SPARK_IMPORT + code, "job.py")


def test_metadata() -> None:
    (rule,) = select_rules(REGISTRY.rules(), select=["DE004"])
    assert rule.name == "select-star-into-write"
    assert rule.severity is Severity.WARNING


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO t SELECT * FROM s",
        "INSERT INTO t (a, b) SELECT * FROM s",
        "INSERT OVERWRITE TABLE t SELECT * FROM s",
        "INSERT INTO t SELECT s.* FROM s",
        "INSERT INTO t SELECT a FROM s UNION ALL SELECT * FROM u",
        "INSERT INTO t SELECT * FROM (SELECT a, b FROM s) AS x",
        "CREATE TABLE t AS SELECT * FROM s",
        "CREATE OR REPLACE TABLE t AS SELECT * FROM s",
    ],
)
def test_star_feeding_a_write_is_flagged(tmp_path: Path, sql: str) -> None:
    result = lint_sql(tmp_path, sql)
    assert result.notices == []
    assert len(result.violations) == 1


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM s",
        "INSERT INTO t SELECT a, b FROM s",
        "INSERT INTO t SELECT a, COUNT(*) AS n FROM s GROUP BY a",
        "INSERT INTO t SELECT a FROM s WHERE EXISTS (SELECT * FROM u WHERE u.id = s.id)",
        "INSERT INTO t SELECT a, b FROM (SELECT * FROM s) AS x",
        "INSERT INTO t VALUES (1, 2)",
        "CREATE VIEW v AS SELECT * FROM s",
        "CREATE TABLE t (a INT, b STRING)",
        "MERGE INTO t USING s ON t.id = s.id WHEN MATCHED THEN UPDATE SET * "
        "WHEN NOT MATCHED THEN INSERT *",
    ],
)
def test_not_flagged_in_sql(tmp_path: Path, sql: str) -> None:
    result = lint_sql(tmp_path, sql)
    assert result.notices == []
    assert result.violations == []


def test_message_names_the_target_table(tmp_path: Path) -> None:
    (violation,) = lint_sql(tmp_path, "\nINSERT INTO gold.Sales SELECT * FROM s").violations
    assert violation.line == 2
    assert "gold.sales" in violation.message


def test_python_points_at_select(tmp_path: Path) -> None:
    (violation,) = lint_py(tmp_path, "df.select('*').write.saveAsTable('t')\n").violations
    assert (violation.line, violation.column) == (2, 4)


def test_python_star_next_to_other_columns(tmp_path: Path) -> None:
    code = "df.select('*', F.lit(1).alias('v')).write.saveAsTable('t')\n"
    assert len(lint_py(tmp_path, code).violations) == 1


@pytest.mark.parametrize(
    "line",
    [
        "df.select('*').show()",
        "df.select('a', 'b').write.saveAsTable('t')",
        "df.select(F.col('*')).count()",
    ],
)
def test_python_not_flagged(tmp_path: Path, line: str) -> None:
    assert lint_py(tmp_path, line + "\n").violations == []


def test_ignored_outside_spark_code(tmp_path: Path) -> None:
    result = lint(tmp_path, "df.select('*').write.saveAsTable('t')\n", "job.py")
    assert result.violations == []

"""Unit tests for DE002 edge cases that are clearer inline than as fixture files."""

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
    rules = select_rules(REGISTRY.rules(), select=["DE002"])
    return lint_paths([path], rules=rules)


def lint_py(tmp_path: Path, code: str) -> LintResult:
    return lint(tmp_path, SPARK_IMPORT + code, "job.py")


def lint_sql(tmp_path: Path, sql: str) -> LintResult:
    return lint(tmp_path, sql, "query.sql")


def test_metadata() -> None:
    (rule,) = select_rules(REGISTRY.rules(), select=["DE002"])
    assert rule.name == "unscoped-overwrite"
    assert rule.severity is Severity.WARNING


# --- PySpark -----------------------------------------------------------------------------------


def test_overwrite_points_at_mode_call(tmp_path: Path) -> None:
    (violation,) = lint_py(tmp_path, "df.write.mode('overwrite').saveAsTable('t')\n").violations
    assert (violation.line, violation.column) == (2, 10)
    assert "partitionBy" not in violation.message


def test_partition_by_trap_is_explained(tmp_path: Path) -> None:
    code = "df.write.mode('overwrite').partitionBy('d').saveAsTable('t')\n"
    (violation,) = lint_py(tmp_path, code).violations
    assert ".partitionBy() alone does not limit" in violation.message


def test_partition_by_before_mode_is_also_explained(tmp_path: Path) -> None:
    code = "df.write.partitionBy('d').mode('overwrite').saveAsTable('t')\n"
    (violation,) = lint_py(tmp_path, code).violations
    assert "partitionBy" in violation.message


@pytest.mark.parametrize(
    "line",
    [
        "df.write.mode('overwrite').option('replaceWhere', 'd = 1').saveAsTable('t')",
        "df.write.option('replaceWhere', 'd = 1').mode('overwrite').saveAsTable('t')",
        "df.write.mode('overwrite').options(replaceWhere='d = 1').saveAsTable('t')",
        "df.write.mode('overwrite').option('partitionOverwriteMode', 'dynamic').save('/p')",
        "df.write.mode('overwrite').options(partitionOverwriteMode='DYNAMIC').save('/p')",
        "df.write.mode('append').saveAsTable('t')",
        "df.write.insertInto('t')",
        "df.writeTo('t').overwritePartitions()",
        "df.writeTo('t').createOrReplace()",
        "df.writeStream.format('delta').mode('overwrite')",
    ],
)
def test_scoped_or_non_overwrite_writes_are_allowed(tmp_path: Path, line: str) -> None:
    assert lint_py(tmp_path, line + "\n").violations == []


def test_static_partition_overwrite_mode_is_still_flagged(tmp_path: Path) -> None:
    code = "df.write.mode('overwrite').option('partitionOverwriteMode', 'static').save('/p')\n"
    assert len(lint_py(tmp_path, code).violations) == 1


def test_insert_into_overwrite_is_flagged_once(tmp_path: Path) -> None:
    assert len(lint_py(tmp_path, "df.write.insertInto('t', True)\n").violations) == 1
    code = "df.write.mode('overwrite').insertInto('t', overwrite=True)\n"
    assert len(lint_py(tmp_path, code).violations) == 1


@pytest.mark.parametrize(
    "setting",
    [
        'spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")',
        "spark.conf.set('spark.sql.sources.partitionOverwriteMode','DYNAMIC')",
        'spark.sql("SET spark.sql.sources.partitionOverwriteMode = dynamic")',
    ],
)
def test_session_dynamic_mode_exempts_the_file(tmp_path: Path, setting: str) -> None:
    code = setting + "\ndf.write.mode('overwrite').saveAsTable('t')\n"
    assert lint_py(tmp_path, code).violations == []


def test_ignored_outside_spark_code(tmp_path: Path) -> None:
    result = lint(tmp_path, "df.write.mode('overwrite').saveAsTable('t')\n", "job.py")
    assert result.violations == []


# --- SQL ---------------------------------------------------------------------------------------


def test_insert_overwrite_without_partition(tmp_path: Path) -> None:
    (violation,) = lint_sql(tmp_path, "INSERT OVERWRITE TABLE gold.sales SELECT 1").violations
    assert violation.line == 1
    assert "gold.sales" in violation.message


def test_insert_overwrite_with_partition(tmp_path: Path) -> None:
    sql = "INSERT OVERWRITE TABLE gold.sales PARTITION (d = '2026-01-01') SELECT 1"
    result = lint_sql(tmp_path, sql)
    assert result.notices == []
    assert result.violations == []


def test_insert_overwrite_with_dynamic_partition_column(tmp_path: Path) -> None:
    sql = "INSERT OVERWRITE TABLE gold.sales PARTITION (d) SELECT 1, d FROM s"
    result = lint_sql(tmp_path, sql)
    assert result.notices == []
    assert result.violations == []


def test_window_partition_in_select_does_not_count(tmp_path: Path) -> None:
    sql = (
        "INSERT OVERWRITE TABLE gold.ranked "
        "SELECT id, ROW_NUMBER() OVER (PARTITION BY d ORDER BY ts) AS rn FROM s"
    )
    assert len(lint_sql(tmp_path, sql).violations) == 1


def test_overwrite_in_embedded_sql(tmp_path: Path) -> None:
    result = lint_py(tmp_path, "spark.sql('INSERT OVERWRITE TABLE t SELECT 1')\n")
    assert [v.line for v in result.violations] == [2]

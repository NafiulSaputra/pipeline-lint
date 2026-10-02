"""Unit tests for DE005 edge cases that are clearer inline than as fixture files."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from pipeline_lint.engine import lint_paths
from pipeline_lint.models import Severity, Violation
from pipeline_lint.rules import REGISTRY, select_rules

SPARK_IMPORT = "from pyspark.sql import SparkSession\n"


def lint(tmp_path: Path, code: str, filename: str = "job.py") -> list[Violation]:
    path = tmp_path / filename
    path.write_text(textwrap.dedent(code), encoding="utf-8")
    rules = select_rules(REGISTRY.rules(), select=["DE005"])
    return lint_paths([path], rules=rules).violations


def test_metadata() -> None:
    (rule,) = select_rules(REGISTRY.rules(), select=["DE005"])
    assert rule.name == "driver-collect"
    assert rule.severity is Severity.WARNING
    assert rule.rationale and rule.bad_example and rule.good_example


def test_column_points_at_method_name(tmp_path: Path) -> None:
    (violation,) = lint(tmp_path, SPARK_IMPORT + "rows = df.collect()\n")
    assert (violation.line, violation.column) == (2, 11)


def test_column_is_counted_in_characters_not_bytes(tmp_path: Path) -> None:
    # "café" is 4 characters but 5 UTF-8 bytes; ast reports byte offsets.
    (violation,) = lint(tmp_path, SPARK_IMPORT + "café = df.collect()\n")
    assert violation.column == 11


def test_multiline_chain_reports_line_of_the_call(tmp_path: Path) -> None:
    code = SPARK_IMPORT + "rows = (\n    df.distinct()\n    .toPandas()\n)\n"
    (violation,) = lint(tmp_path, code)
    assert (violation.line, violation.column) == (4, 6)


def test_ignored_without_spark_import(tmp_path: Path) -> None:
    assert lint(tmp_path, "rows = df.collect()\n") == []


@pytest.mark.parametrize(
    "import_line",
    [
        "import pyspark\n",
        "from pyspark.sql import functions as F\n",
        "from databricks.connect import DatabricksSession\n",
    ],
)
def test_spark_detected_from_imports(tmp_path: Path, import_line: str) -> None:
    assert len(lint(tmp_path, import_line + "rows = df.collect()\n")) == 1


def test_databricks_notebook_without_imports(tmp_path: Path) -> None:
    code = "# Databricks notebook source\nrows = spark.table('t').collect()\n"
    assert len(lint(tmp_path, code)) == 1


def test_limit_through_reassigned_variable(tmp_path: Path) -> None:
    code = SPARK_IMPORT + "df = spark.table('t')\ndf = df.limit(10)\nrows = df.collect()\n"
    assert lint(tmp_path, code) == []


def test_unbounded_variable_is_flagged(tmp_path: Path) -> None:
    code = SPARK_IMPORT + "df = spark.table('t')\ndf = df.filter('x > 1')\nrows = df.collect()\n"
    assert len(lint(tmp_path, code)) == 1


def test_global_aggregate_is_allowed(tmp_path: Path) -> None:
    code = SPARK_IMPORT + "max_ts = df.agg({'ts': 'max'}).collect()[0][0]\n"
    assert lint(tmp_path, code) == []


@pytest.mark.parametrize("grouping", ["groupBy", "groupby", "rollup", "cube"])
def test_grouped_aggregate_is_flagged(tmp_path: Path, grouping: str) -> None:
    code = SPARK_IMPORT + f"rows = df.{grouping}('k').agg({{'v': 'sum'}}).collect()\n"
    assert len(lint(tmp_path, code)) == 1


def test_call_with_arguments_is_not_a_dataframe_action(tmp_path: Path) -> None:
    assert lint(tmp_path, SPARK_IMPORT + "values = stats.collect(5)\n") == []


def test_self_referencing_assignment_terminates(tmp_path: Path) -> None:
    code = SPARK_IMPORT + "df = df\nrows = df.collect()\n"
    assert len(lint(tmp_path, code)) == 1

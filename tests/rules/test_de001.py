"""Unit tests for DE001 edge cases that are clearer inline than as fixture files."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from pipeline_lint.engine import LintResult, lint_paths
from pipeline_lint.models import Severity
from pipeline_lint.rules import REGISTRY, select_rules

SPARK_IMPORT = "from pyspark.sql import SparkSession\n"


def lint(tmp_path: Path, code: str, filename: str, dialect: str = "spark") -> LintResult:
    path = tmp_path / filename
    path.write_text(textwrap.dedent(code), encoding="utf-8")
    rules = select_rules(REGISTRY.rules(), select=["DE001"])
    return lint_paths([path], rules=rules, sql_dialect=dialect)


def lint_sql(tmp_path: Path, sql: str, dialect: str = "spark") -> LintResult:
    return lint(tmp_path, sql, "query.sql", dialect)


def lint_py(tmp_path: Path, code: str) -> LintResult:
    return lint(tmp_path, code, "job.py")


def test_metadata() -> None:
    (rule,) = select_rules(REGISTRY.rules(), select=["DE001"])
    assert rule.name == "non-idempotent-append"
    assert rule.severity is Severity.ERROR


# --- SQL ---------------------------------------------------------------------------------------


def test_plain_insert_is_flagged_with_table_name_and_position(tmp_path: Path) -> None:
    sql = "SELECT 1;\n\n  INSERT INTO sales.orders SELECT * FROM raw.orders;\n"
    result = lint_sql(tmp_path, sql)
    (violation,) = result.violations
    assert (violation.line, violation.column) == (3, 3)
    assert "sales.orders" in violation.message


def test_insert_values_is_flagged(tmp_path: Path) -> None:
    result = lint_sql(tmp_path, "INSERT INTO audit_log VALUES (1, 'loaded');")
    assert len(result.violations) == 1


def test_delete_before_insert_same_table(tmp_path: Path) -> None:
    sql = "DELETE FROM sales.orders WHERE d = '2026-01-01';\nINSERT INTO sales.orders SELECT 1;"
    assert lint_sql(tmp_path, sql).violations == []


def test_delete_after_insert_does_not_help(tmp_path: Path) -> None:
    sql = "INSERT INTO sales.orders SELECT 1;\nDELETE FROM sales.orders WHERE d = 1;"
    assert len(lint_sql(tmp_path, sql).violations) == 1


def test_delete_of_another_table_does_not_help(tmp_path: Path) -> None:
    sql = "DELETE FROM sales.payments;\nINSERT INTO sales.orders SELECT 1;"
    assert len(lint_sql(tmp_path, sql).violations) == 1


def test_table_names_match_case_insensitively_and_by_suffix(tmp_path: Path) -> None:
    sql = "DELETE FROM ORDERS;\nINSERT INTO prod.sales.orders SELECT 1;"
    assert lint_sql(tmp_path, sql).violations == []


def test_truncate_before_insert(tmp_path: Path) -> None:
    sql = "TRUNCATE TABLE sales.orders;\nINSERT INTO sales.orders SELECT 1;"
    assert lint_sql(tmp_path, sql).violations == []


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT OVERWRITE TABLE sales.orders SELECT 1",
        "INSERT OVERWRITE TABLE sales.orders PARTITION (d = '2026-01-01') SELECT 1",
        "MERGE INTO t USING s ON t.id = s.id WHEN NOT MATCHED THEN INSERT *",
    ],
)
def test_idempotent_spark_statements(tmp_path: Path, sql: str) -> None:
    result = lint_sql(tmp_path, sql)
    assert result.notices == []
    assert result.violations == []


def test_databricks_replace_where(tmp_path: Path) -> None:
    sql = "INSERT INTO sales.orders REPLACE WHERE d = '2026-01-01' SELECT * FROM staging.orders"
    result = lint_sql(tmp_path, sql, dialect="databricks")
    assert result.notices == []
    assert result.violations == []


def test_postgres_on_conflict(tmp_path: Path) -> None:
    sql = "INSERT INTO orders (id, amount) VALUES (1, 10) ON CONFLICT (id) DO NOTHING"
    result = lint_sql(tmp_path, sql, dialect="postgres")
    assert result.notices == []
    assert result.violations == []


def test_sqlite_insert_or_replace(tmp_path: Path) -> None:
    result = lint_sql(tmp_path, "INSERT OR REPLACE INTO orders VALUES (1, 10)", dialect="sqlite")
    assert result.notices == []
    assert result.violations == []


def test_templated_sql_is_parsed(tmp_path: Path) -> None:
    sql = """
    {% if params.full_refresh %}
    -- nothing
    {% endif %}
    INSERT INTO sales.orders
    SELECT * FROM raw.orders
    WHERE order_date = '{{ ds }}' AND region = ${region};
    """
    result = lint_sql(tmp_path, sql)
    assert result.notices == []
    assert [v.line for v in result.violations] == [5]


def test_unparsable_statement_becomes_notice_and_rest_is_checked(tmp_path: Path) -> None:
    sql = "INSERT INTO ((( broken;\nINSERT INTO sales.orders SELECT 1;"
    result = lint_sql(tmp_path, sql)
    assert [n.line for n in result.notices] == [1]
    assert [v.line for v in result.violations] == [2]


# --- PySpark -----------------------------------------------------------------------------------


def test_append_mode_points_at_mode_call(tmp_path: Path) -> None:
    code = SPARK_IMPORT + "df.write.format('delta').mode('append').saveAsTable('t')\n"
    (violation,) = lint_py(tmp_path, code).violations
    assert (violation.line, violation.column) == (2, 26)
    assert '.mode("append")' in violation.message


def test_append_mode_keyword_and_case(tmp_path: Path) -> None:
    code = SPARK_IMPORT + "df.write.mode(saveMode='APPEND').parquet('/data/out')\n"
    assert len(lint_py(tmp_path, code).violations) == 1


def test_append_through_writer_variable(tmp_path: Path) -> None:
    code = SPARK_IMPORT + "writer = df.write\nwriter.mode('append').saveAsTable('t')\n"
    assert len(lint_py(tmp_path, code).violations) == 1


@pytest.mark.parametrize(
    "line",
    [
        "df.write.mode('overwrite').saveAsTable('t')",
        "df.write.insertInto('t', True)",
        "df.write.insertInto('t', overwrite=True)",
        "df.write.mode('overwrite').insertInto('t')",
        "df.writeStream.outputMode('append').toTable('t')",
        "df.writeStream.format('delta').mode('append')",
        "items.append(1)",
        "df.writeTo('t').overwritePartitions()",
    ],
)
def test_non_append_writes_are_allowed(tmp_path: Path, line: str) -> None:
    assert lint_py(tmp_path, SPARK_IMPORT + line + "\n").violations == []


def test_insert_into_without_overwrite(tmp_path: Path) -> None:
    (violation,) = lint_py(tmp_path, SPARK_IMPORT + "df.write.insertInto('t')\n").violations
    assert ".insertInto()" in violation.message


def test_writer_v2_append(tmp_path: Path) -> None:
    (violation,) = lint_py(tmp_path, SPARK_IMPORT + "df.writeTo('t').append()\n").violations
    assert ".writeTo(...).append()" in violation.message


def test_delete_in_spark_sql_before_append(tmp_path: Path) -> None:
    code = SPARK_IMPORT + (
        "spark.sql('DELETE FROM silver.orders WHERE d = 1')\n"
        "df.write.mode('append').saveAsTable('silver.orders')\n"
    )
    assert lint_py(tmp_path, code).violations == []


def test_delete_in_spark_sql_after_append_does_not_help(tmp_path: Path) -> None:
    code = SPARK_IMPORT + (
        "df.write.mode('append').saveAsTable('silver.orders')\n"
        "spark.sql('DELETE FROM silver.orders WHERE d = 1')\n"
    )
    assert len(lint_py(tmp_path, code).violations) == 1


def test_append_ignored_outside_spark_code(tmp_path: Path) -> None:
    assert lint_py(tmp_path, "df.write.mode('append').saveAsTable('t')\n").violations == []


def test_embedded_sql_line_mapping(tmp_path: Path) -> None:
    code = SPARK_IMPORT + 'spark.sql("""\n    SELECT 1;\n    INSERT INTO t SELECT 2\n""")\n'
    (violation,) = lint_py(tmp_path, code).violations
    assert violation.line == 4


def test_embedded_sql_through_variable(tmp_path: Path) -> None:
    code = SPARK_IMPORT + "query = 'INSERT INTO t SELECT 1'\nspark.sql(query)\n"
    (violation,) = lint_py(tmp_path, code).violations
    assert violation.line == 2


def test_fstring_sql_is_not_parsed(tmp_path: Path) -> None:
    code = SPARK_IMPORT + "spark.sql(f'INSERT INTO {table} SELECT 1')\n"
    result = lint_py(tmp_path, code)
    assert result.violations == []
    assert result.notices == []

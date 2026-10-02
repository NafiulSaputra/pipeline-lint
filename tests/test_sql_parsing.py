from __future__ import annotations

from pathlib import Path

from sqlglot import exp

from pipeline_lint.parsing.databricks import iter_magic_sql_cells
from pipeline_lint.parsing.sql import (
    TEMPLATE_PLACEHOLDER,
    TableName,
    mask_templating,
    parse_sql,
)

PATH = Path("query.sql")


def test_statements_are_split_with_file_lines() -> None:
    sql = "-- header\nSELECT 1;\n\nSELECT\n  2;\nSELECT 3"
    statements, notices = parse_sql(sql, path=PATH, first_line=1, origin="sql_file")
    assert notices == []
    assert [s.line for s in statements] == [2, 4, 6]
    assert all(isinstance(s.expression, exp.Select) for s in statements)


def test_first_line_offsets_extracted_sql() -> None:
    statements, _ = parse_sql("\nSELECT 1", path=PATH, first_line=10, origin="spark_sql")
    assert statements[0].line == 11
    assert statements[0].column == 1


def test_semicolon_inside_string_does_not_split() -> None:
    statements, _ = parse_sql("SELECT 'a;b'; SELECT 2", path=PATH, first_line=1, origin="sql_file")
    assert len(statements) == 2


def test_mask_templating_keeps_line_numbers() -> None:
    sql = "SELECT '{{ ds }}',\n{{\n macro()\n}} FROM t {% if x %}\n{# note #}${var}"
    masked = mask_templating(sql)
    assert masked.count("\n") == sql.count("\n")
    assert "{" not in masked
    assert TEMPLATE_PLACEHOLDER in masked


def test_table_name_matching() -> None:
    orders = TableName.from_string("orders")
    assert orders is not None
    assert orders.matches(TableName(("prod", "sales", "orders")))
    assert TableName(("sales", "orders")).matches(TableName(("prod", "sales", "orders")))
    assert not TableName(("sales", "orders")).matches(TableName(("hr", "orders")))
    assert TableName.from_string("`Sales`.`Orders`") == TableName(("sales", "orders"))
    assert TableName.from_string("") is None


def test_magic_sql_cells_map_to_notebook_lines() -> None:
    notebook = "\n".join(
        [
            "# Databricks notebook source",  # 1
            "# MAGIC %md",  # 2
            "# MAGIC Some text",  # 3
            "",  # 4
            "# COMMAND ----------",  # 5
            "",  # 6
            "# MAGIC %sql",  # 7
            "# MAGIC SELECT 1;",  # 8
            "# MAGIC SELECT 2",  # 9
            "",  # 10
            "# COMMAND ----------",  # 11
            "# MAGIC %sql SELECT 3",  # 12
        ]
    )
    cells = list(iter_magic_sql_cells(notebook))
    assert [first_line for _, first_line in cells] == [7, 12]

    sql, first_line = cells[0]
    statements, _ = parse_sql(sql, path=PATH, first_line=first_line, origin="notebook_magic")
    assert [s.line for s in statements] == [8, 9]

    sql, first_line = cells[1]
    statements, _ = parse_sql(sql, path=PATH, first_line=first_line, origin="notebook_magic")
    assert [s.line for s in statements] == [12]

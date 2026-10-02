from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from pipeline_lint.engine import lint_paths, lint_source
from pipeline_lint.errors import RuleCrashError
from pipeline_lint.models import Severity, SourceFile, Violation
from pipeline_lint.parsing import load_source
from pipeline_lint.rules import Rule


class AlwaysFlag(Rule):
    id = "DE900"
    name = "always-flag"
    severity = Severity.ERROR
    summary = rationale = bad_example = good_example = "test rule"

    def check_python(self, source: SourceFile) -> Iterator[Violation]:
        yield self.violation(source, line=1, column=1, message="flagged")


class Crashes(Rule):
    id = "DE901"
    name = "crashes"
    severity = Severity.WARNING
    summary = rationale = bad_example = good_example = "test rule"

    def check_python(self, source: SourceFile) -> Iterator[Violation]:
        raise RuntimeError("boom")


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_violations_are_sorted_and_counted(tmp_path: Path) -> None:
    write(tmp_path / "b.py", "x = 1\n")
    write(tmp_path / "a.py", "x = 1\n")

    result = lint_paths([tmp_path], rules=[AlwaysFlag()])

    assert [v.path.name for v in result.violations] == ["a.py", "b.py"]
    assert result.files_checked == 2
    assert result.error_count == 2
    assert result.warning_count == 0
    assert result.files_with_violations == 2


def test_syntax_error_is_skipped_not_fatal(tmp_path: Path) -> None:
    write(tmp_path / "broken.py", "def broken(:\n")
    write(tmp_path / "fine.py", "x = 1\n")

    result = lint_paths([tmp_path], rules=[AlwaysFlag()])

    assert result.files_checked == 1
    assert [s.path.name for s in result.skipped] == ["broken.py"]
    assert "syntax error at line 1" in result.skipped[0].reason


def test_non_utf8_file_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "latin1.py").write_bytes("nome = 'ção'\n".encode("latin-1"))
    result = lint_paths([tmp_path], rules=[AlwaysFlag()])
    assert result.skipped and "UTF-8" in result.skipped[0].reason


def test_rule_crash_is_reported_with_rule_and_file(tmp_path: Path) -> None:
    source = load_source(write(tmp_path / "job.py", "x = 1\n"))
    with pytest.raises(RuleCrashError) as excinfo:
        lint_source(source, [Crashes()])
    assert excinfo.value.rule_id == "DE901"
    assert excinfo.value.path == source.path


def test_sql_files_are_loaded(tmp_path: Path) -> None:
    source = load_source(write(tmp_path / "q.sql", "SELECT 1;\n"))
    assert source.kind == "sql"
    assert source.python_ast is None


def test_databricks_notebook_is_classified(tmp_path: Path) -> None:
    text = "\n# Databricks notebook source\nx = 1\n"
    source = load_source(write(tmp_path / "nb.py", text))
    assert source.kind == "databricks_notebook"
    assert source.is_python


def test_byte_order_mark_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "bom.py"
    path.write_bytes(b"\xef\xbb\xbf# Databricks notebook source\nx = 1\n")
    assert load_source(path).kind == "databricks_notebook"

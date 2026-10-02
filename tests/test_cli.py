from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from pipeline_lint import __version__
from pipeline_lint.cli import EXIT_ERROR, EXIT_OK, EXIT_VIOLATIONS, app

FIXTURES = Path(__file__).resolve().parent / "fixtures"
COLLECT_FIXTURE = str(FIXTURES / "DE005" / "bad_collect_to_driver.py")  # 3 DE005 warnings
APPEND_FIXTURE = str(FIXTURES / "DE001" / "bad_daily_load.sql")  # 2 DE001 errors
runner = CliRunner()


def run(*args: str) -> Any:
    return runner.invoke(app, list(args))


def test_violations_exit_1_and_are_printed() -> None:
    result = run("check", COLLECT_FIXTURE)
    assert result.exit_code == EXIT_VIOLATIONS, result.output
    assert "DE005" in result.output
    assert "Found 3 violations (0 errors, 3 warnings) in 1 file." in result.output


def test_clean_file_exits_0() -> None:
    result = run("check", str(FIXTURES / "DE005" / "good_bounded_actions.py"))
    assert result.exit_code == EXIT_OK, result.output
    assert "All checks passed (1 file checked)." in result.output


def test_missing_path_is_a_usage_error(tmp_path: Path) -> None:
    assert run("check", str(tmp_path / "missing")).exit_code == EXIT_ERROR


def test_skipped_file_is_reported(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    result = run("check", str(tmp_path))
    assert result.exit_code == EXIT_OK
    assert "skipped" in result.output


# --- formats -------------------------------------------------------------------------------------


def test_json_format() -> None:
    result = run("check", COLLECT_FIXTURE, "--format", "json")
    assert result.exit_code == EXIT_VIOLATIONS
    report = json.loads(result.stdout)
    assert report["summary"]["warnings"] == 3
    assert {v["rule_id"] for v in report["violations"]} == {"DE005"}


def test_sarif_format_to_file(tmp_path: Path) -> None:
    output = tmp_path / "results.sarif"
    result = run("check", APPEND_FIXTURE, "-f", "SARIF", "-o", str(output))
    assert result.exit_code == EXIT_VIOLATIONS
    assert result.stdout.strip() == ""
    log = json.loads(output.read_text(encoding="utf-8"))
    assert [r["ruleId"] for r in log["runs"][0]["results"]] == ["DE001", "DE001"]


def test_text_format_to_file(tmp_path: Path) -> None:
    output = tmp_path / "report.txt"
    result = run("check", COLLECT_FIXTURE, "--output", str(output))
    assert result.exit_code == EXIT_VIOLATIONS
    text = output.read_text(encoding="utf-8")
    assert "DE005" in text
    assert "\x1b[" not in text  # no terminal colour codes in files


# --- selection and thresholds ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("args", "exit_code"),
    [
        (["--select", "DE001"], EXIT_OK),
        (["--select", "de00"], EXIT_VIOLATIONS),
        (["--ignore", "DE005"], EXIT_OK),
        (["--fail-on", "error"], EXIT_OK),
        (["--fail-on", "warning"], EXIT_VIOLATIONS),
    ],
)
def test_selection_and_fail_on(args: list[str], exit_code: int) -> None:
    assert run("check", COLLECT_FIXTURE, *args).exit_code == exit_code


def test_fail_on_error_still_fails_on_errors() -> None:
    assert run("check", APPEND_FIXTURE, "--fail-on", "error").exit_code == EXIT_VIOLATIONS


def test_config_file(tmp_path: Path) -> None:
    config = tmp_path / "pyproject.toml"
    config.write_text('[tool.pipeline-lint]\nignore = ["DE005"]\n', encoding="utf-8")
    assert run("check", COLLECT_FIXTURE, "--config", str(config)).exit_code == EXIT_OK


@pytest.mark.parametrize(
    "args",
    [
        ["--select", "XX1"],
        ["--sql-dialect", "not-a-dialect"],
        ["--fail-on", "info"],
    ],
)
def test_invalid_options_exit_2(args: list[str]) -> None:
    assert run("check", COLLECT_FIXTURE, *args).exit_code == EXIT_ERROR


def test_invalid_config_file_exits_2(tmp_path: Path) -> None:
    config = tmp_path / "pyproject.toml"
    config.write_text("[tool.pipeline-lint]\nunknown = 1\n", encoding="utf-8")
    result = run("check", COLLECT_FIXTURE, "--config", str(config))
    assert result.exit_code == EXIT_ERROR
    assert "unknown option" in result.output


def test_noqa_is_reported_in_summary(tmp_path: Path) -> None:
    job = tmp_path / "job.py"
    job.write_text(
        "from pyspark.sql import SparkSession\nrows = df.collect()  # noqa: DE005\n",
        encoding="utf-8",
    )
    result = run("check", str(job))
    assert result.exit_code == EXIT_OK
    assert "1 suppressed by noqa" in result.output


# --- other commands ----------------------------------------------------------------------------


def test_rules_command_lists_builtin_rules() -> None:
    result = run("rules")
    assert result.exit_code == EXIT_OK
    for rule_id in ["DE001", "DE002", "DE003", "DE004", "DE005", "DE006", "DE007"]:
        assert rule_id in result.output


def test_version() -> None:
    result = run("--version")
    assert result.exit_code == EXIT_OK
    assert __version__ in result.output

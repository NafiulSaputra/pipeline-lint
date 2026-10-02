from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from pipeline_lint import __version__
from pipeline_lint.cli import EXIT_ERROR, EXIT_OK, EXIT_VIOLATIONS, app

FIXTURES = Path(__file__).resolve().parent / "fixtures"
runner = CliRunner()


def test_violations_exit_1_and_are_printed() -> None:
    result = runner.invoke(app, ["check", str(FIXTURES / "DE005" / "bad_collect_to_driver.py")])

    assert result.exit_code == EXIT_VIOLATIONS, result.output
    assert "DE005" in result.output
    assert "Found 3 violations (0 errors, 3 warnings) in 1 file." in result.output


def test_clean_file_exits_0() -> None:
    result = runner.invoke(app, ["check", str(FIXTURES / "DE005" / "good_bounded_actions.py")])

    assert result.exit_code == EXIT_OK, result.output
    assert "All checks passed (1 file checked)." in result.output


def test_missing_path_is_a_usage_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["check", str(tmp_path / "missing")])
    assert result.exit_code == EXIT_ERROR


def test_skipped_file_is_reported(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    result = runner.invoke(app, ["check", str(tmp_path)])
    assert result.exit_code == EXIT_OK
    assert "skipped" in result.output


def test_rules_command_lists_builtin_rules() -> None:
    result = runner.invoke(app, ["rules"])
    assert result.exit_code == EXIT_OK
    assert "DE005" in result.output
    assert "driver-collect" in result.output


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == EXIT_OK
    assert __version__ in result.output

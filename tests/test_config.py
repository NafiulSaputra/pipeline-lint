from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline_lint.config import Config, find_pyproject, load_config, with_overrides
from pipeline_lint.errors import ConfigError
from pipeline_lint.models import Severity


def write_pyproject(directory: Path, body: str) -> Path:
    path = directory / "pyproject.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_defaults_without_section(tmp_path: Path) -> None:
    path = write_pyproject(tmp_path, '[project]\nname = "demo"\n')
    config = load_config(path)
    assert config.select is None
    assert config.ignore == ()
    assert config.sql_dialect == "spark"
    assert config.fail_on is Severity.WARNING
    assert config.root == tmp_path.resolve()


def test_full_section(tmp_path: Path) -> None:
    path = write_pyproject(
        tmp_path,
        """
[tool.pipeline-lint]
select = ["DE00"]
ignore = ["de005"]
exclude = ["notebooks/scratch/**"]
sql-dialect = "databricks"
fail-on = "error"
""",
    )
    config = load_config(path)
    assert config.select == ("DE00",)
    assert config.ignore == ("DE005",)
    assert config.exclude == ("notebooks/scratch/**",)
    assert config.sql_dialect == "databricks"
    assert config.fail_on is Severity.ERROR


def test_found_from_subdirectory(tmp_path: Path) -> None:
    path = write_pyproject(tmp_path, '[tool.pipeline-lint]\nignore = ["DE003"]\n')
    nested = tmp_path / "pipelines" / "daily"
    nested.mkdir(parents=True)
    assert find_pyproject(nested) == path.resolve()
    assert load_config(start=nested).ignore == ("DE003",)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('[tool.pipeline-lint]\nselct = ["DE001"]\n', "unknown option(s)"),
        ('[tool.pipeline-lint]\nselect = "DE001"\n', "must be a list of strings"),
        ('[tool.pipeline-lint]\nignore = ["XX001"]\n', "invalid rule selector"),
        ('[tool.pipeline-lint]\nfail-on = "info"\n', "invalid fail-on"),
        ('[tool.pipeline-lint]\nsql-dialect = "not-a-dialect"\n', "unknown SQL dialect"),
        ("[tool.pipeline-lint\n", "cannot read"),
    ],
)
def test_invalid_config(tmp_path: Path, body: str, message: str) -> None:
    path = write_pyproject(tmp_path, body)
    with pytest.raises(ConfigError, match=re.escape(message)):
        load_config(path)


def test_explicit_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.toml")


def test_overrides() -> None:
    base = Config(select=("DE001",), ignore=("DE003",))
    updated = with_overrides(
        base, select=["de002", "DE004"], ignore=["DE005"], fail_on=Severity.ERROR
    )
    assert updated.select == ("DE002", "DE004")
    assert updated.ignore == ("DE003", "DE005")
    assert updated.fail_on is Severity.ERROR
    assert with_overrides(base) == base

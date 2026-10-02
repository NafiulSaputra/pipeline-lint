"""Unit tests for the Airflow rules DE006 and DE007."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from pipeline_lint.engine import LintResult, lint_paths
from pipeline_lint.models import Severity
from pipeline_lint.rules import REGISTRY, select_rules

AIRFLOW_IMPORT = "from airflow import DAG\n"


def lint(tmp_path: Path, code: str, rule_id: str, header: str = AIRFLOW_IMPORT) -> LintResult:
    path = tmp_path / "dag.py"
    path.write_text(header + textwrap.dedent(code), encoding="utf-8")
    return lint_paths([path], rules=select_rules(REGISTRY.rules(), select=[rule_id]))


@pytest.mark.parametrize(
    ("rule_id", "name", "severity"),
    [
        ("DE006", "airflow-missing-retries", Severity.WARNING),
        ("DE007", "airflow-unsafe-catchup", Severity.ERROR),
    ],
)
def test_metadata(rule_id: str, name: str, severity: Severity) -> None:
    (rule,) = select_rules(REGISTRY.rules(), select=[rule_id])
    assert (rule.name, rule.severity) == (name, severity)


# --- DE006 -------------------------------------------------------------------------------------


def test_de006_points_at_dag_name(tmp_path: Path) -> None:
    (violation,) = lint(tmp_path, "d = DAG('x')\n", "DE006").violations
    assert (violation.line, violation.column) == (2, 5)
    assert "no retries" in violation.message


def test_de006_attribute_dag(tmp_path: Path) -> None:
    code = "import airflow\nd = airflow.DAG('x')\n"
    (violation,) = lint(tmp_path, code, "DE006", header="").violations
    assert (violation.line, violation.column) == (2, 13)


def test_de006_bare_decorator(tmp_path: Path) -> None:
    code = "@dag\ndef pipeline():\n    pass\n"
    result = lint(tmp_path, code, "DE006", header="from airflow.decorators import dag\n")
    assert [v.line for v in result.violations] == [2]


def test_de006_retries_zero(tmp_path: Path) -> None:
    (violation,) = lint(tmp_path, "d = DAG('x', default_args={'retries': 0})\n", "DE006").violations
    assert "retries to 0" in violation.message


@pytest.mark.parametrize(
    "code",
    [
        "d = DAG('x', default_args={'retries': 1})\n",
        "d = DAG('x', default_args=dict(retries=3))\n",
        "n = 2\nd = DAG('x', default_args={'retries': n})\n",
        "args = {'retries': 2}\nargs2 = args\nd = DAG('x', default_args=args2)\n",
        "d = DAG('x', default_args=get_default_args())\n",
        "d = DAG('x', default_args=dict(**base))\n",
        "d = DAG(**config)\n",
    ],
)
def test_de006_not_flagged(tmp_path: Path, code: str) -> None:
    assert lint(tmp_path, code, "DE006").violations == []


def test_de006_ignored_without_airflow_import(tmp_path: Path) -> None:
    assert lint(tmp_path, "d = DAG('x')\n", "DE006", header="").violations == []


# --- DE007 -------------------------------------------------------------------------------------


def test_de007_points_at_catchup_value(tmp_path: Path) -> None:
    code = "d = DAG('x', catchup=True)\n"
    (violation,) = lint(tmp_path, code, "DE007").violations
    assert (violation.line, violation.column) == (2, 22)
    assert "no start_date" in violation.message


@pytest.mark.parametrize(
    "start",
    [
        "datetime.now()",
        "datetime.utcnow()",
        "datetime.today() - timedelta(days=1)",
        "pendulum.now('UTC')",
        "pendulum.today()",
        "timezone.utcnow()",
        "days_ago(1)",
        "dates.days_ago(1)",
    ],
)
def test_de007_dynamic_start_dates(tmp_path: Path, start: str) -> None:
    code = f"d = DAG('x', start_date={start}, catchup=True)\n"
    (violation,) = lint(tmp_path, code, "DE007").violations
    assert "changes on every parse" in violation.message


def test_de007_dynamic_start_date_in_default_args(tmp_path: Path) -> None:
    code = "args = {'start_date': days_ago(1)}\nd = DAG('x', default_args=args, catchup=True)\n"
    assert len(lint(tmp_path, code, "DE007").violations) == 1


@pytest.mark.parametrize(
    "code",
    [
        "d = DAG('x', start_date=datetime(2026, 1, 1), catchup=True)\n",
        "d = DAG('x', start_date=pendulum.datetime(2026, 1, 1, tz='UTC'), catchup=True)\n",
        "d = DAG('x', start_date=datetime.now(), catchup=False)\n",
        "d = DAG('x', start_date=datetime.now())\n",
        "d = DAG('x', default_args=imported_args, catchup=True)\n",
        "d = DAG('x', catchup=enable_catchup)\n",
    ],
)
def test_de007_not_flagged(tmp_path: Path, code: str) -> None:
    assert lint(tmp_path, code, "DE007").violations == []

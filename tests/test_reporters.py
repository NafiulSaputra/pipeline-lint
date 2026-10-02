from __future__ import annotations

import json
from pathlib import Path

from pipeline_lint.engine import LintResult
from pipeline_lint.models import ParseNotice, Severity, SkippedFile, Violation
from pipeline_lint.reporters.json import render_json
from pipeline_lint.reporters.sarif import render_sarif
from pipeline_lint.rules import REGISTRY

RESULT = LintResult(
    violations=[
        Violation(Path("jobs/load.sql"), 3, 1, "DE001", Severity.ERROR, "appends rows"),
        Violation(Path("jobs/ä job.py"), 7, 12, "DE005", Severity.WARNING, "collect"),
    ],
    files_checked=4,
    skipped=[SkippedFile(Path("broken.py"), "Python syntax error at line 1: invalid syntax")],
    notices=[ParseNotice(Path("jobs/odd.sql"), 2, "SQL statement skipped, cannot parse: x")],
    suppressed=2,
)


def test_json_report() -> None:
    report = json.loads(render_json(RESULT))
    assert report["schema_version"] == 1
    assert report["tool"]["name"] == "pipeline-lint"
    assert report["summary"] == {
        "files_checked": 4,
        "files_skipped": 1,
        "violations": 2,
        "errors": 1,
        "warnings": 1,
        "suppressed": 2,
    }
    first = report["violations"][0]
    assert first == {
        "rule_id": "DE001",
        "severity": "error",
        "path": "jobs/load.sql",
        "line": 3,
        "column": 1,
        "message": "appends rows",
    }
    assert report["notices"][0]["line"] == 2
    assert report["skipped"][0]["path"] == "broken.py"


def test_sarif_report_structure() -> None:
    rules = REGISTRY.rules()
    log = json.loads(render_sarif(RESULT, rules))

    assert log["version"] == "2.1.0"
    assert log["$schema"].endswith("sarif-2.1.0.json")
    (run,) = log["runs"]
    driver = run["tool"]["driver"]
    assert driver["name"] == "pipeline-lint"
    assert [r["id"] for r in driver["rules"]] == [rule.id for rule in rules]
    assert run["columnKind"] == "unicodeCodePoints"

    for descriptor in driver["rules"]:
        assert descriptor["shortDescription"]["text"]
        assert descriptor["help"]["markdown"]
        assert descriptor["helpUri"].endswith(f"/docs/rules/{descriptor['id']}.md")
        assert descriptor["defaultConfiguration"]["level"] in {"error", "warning"}


def test_sarif_results() -> None:
    rules = REGISTRY.rules()
    (run,) = json.loads(render_sarif(RESULT, rules))["runs"]
    first, second = run["results"]

    assert first["ruleId"] == "DE001"
    assert first["level"] == "error"
    assert rules[first["ruleIndex"]].id == "DE001"
    location = first["locations"][0]["physicalLocation"]
    assert location["artifactLocation"]["uri"] == "jobs/load.sql"
    assert location["region"] == {"startLine": 3, "startColumn": 1}

    assert second["level"] == "warning"
    # Spaces and non-ASCII characters are percent-encoded in URIs.
    assert second["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == (
        "jobs/%C3%A4%20job.py"
    )


def test_sarif_notifications_for_notices_and_skipped_files() -> None:
    (run,) = json.loads(render_sarif(RESULT, REGISTRY.rules()))["runs"]
    (invocation,) = run["invocations"]
    assert invocation["executionSuccessful"] is True
    texts = [n["message"]["text"] for n in invocation["toolExecutionNotifications"]]
    assert texts[0].startswith("SQL statement skipped")
    assert texts[1].startswith("File skipped")

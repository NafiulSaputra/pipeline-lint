"""SARIF 2.1.0 output, the format GitHub code scanning (and many other tools) consume."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pipeline_lint import __version__
from pipeline_lint.engine import LintResult
from pipeline_lint.models import Severity
from pipeline_lint.reporters import relative_posix
from pipeline_lint.rules import Rule

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
REPOSITORY_URL = "https://github.com/NafiulSaputra/pipeline-lint"


def rule_help_uri(rule_id: str) -> str:
    return f"{REPOSITORY_URL}/blob/main/docs/rules/{rule_id}.md"


def render_sarif(result: LintResult, rules: Sequence[Rule]) -> str:
    """Render a SARIF log with one run.

    All active rules are listed in ``tool.driver.rules`` (not only those that fired), so a
    viewer can show documentation for every rule. Unparsable SQL and skipped files become
    tool notifications: visible, but not results, because the linter makes no claim about
    code it could not read.
    """
    rule_index = {rule.id: index for index, rule in enumerate(rules)}

    results: list[dict[str, Any]] = []
    for violation in result.violations:
        entry: dict[str, Any] = {
            "ruleId": violation.rule_id,
            "level": _level(violation.severity),
            "message": {"text": violation.message},
            "locations": [_location(violation.path, violation.line, violation.column)],
        }
        if violation.rule_id in rule_index:
            entry["ruleIndex"] = rule_index[violation.rule_id]
        results.append(entry)

    notifications = [
        {
            "level": "warning",
            "message": {"text": notice.message},
            "locations": [_location(notice.path, notice.line, None)],
        }
        for notice in result.notices
    ] + [
        {
            "level": "warning",
            "message": {"text": f"File skipped: {skipped.reason}"},
            "locations": [_location(skipped.path, None, None)],
        }
        for skipped in result.skipped
    ]

    log = {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "pipeline-lint",
                        "version": __version__,
                        "informationUri": REPOSITORY_URL,
                        "rules": [_rule_descriptor(rule) for rule in rules],
                    }
                },
                # Columns are counted in characters, not bytes or UTF-16 units.
                "columnKind": "unicodeCodePoints",
                "results": results,
                "invocations": [
                    {
                        "executionSuccessful": True,
                        "toolExecutionNotifications": notifications,
                    }
                ],
            }
        ],
    }
    return json.dumps(log, indent=2, ensure_ascii=False)


def _rule_descriptor(rule: Rule) -> dict[str, Any]:
    markdown = (
        f"{rule.rationale}\n\n"
        f"**Problematic:**\n\n```\n{rule.bad_example}\n```\n\n"
        f"**Better:**\n\n```\n{rule.good_example}\n```"
    )
    return {
        "id": rule.id,
        "name": rule.name,
        "shortDescription": {"text": rule.summary},
        "fullDescription": {"text": rule.rationale},
        "help": {"text": rule.rationale, "markdown": markdown},
        "helpUri": rule_help_uri(rule.id),
        "defaultConfiguration": {"level": _level(rule.severity)},
        "properties": {"tags": ["data-engineering", "reliability"]},
    }


def _level(severity: Severity) -> str:
    return "error" if severity is Severity.ERROR else "warning"


def _location(path: Path, line: int | None, column: int | None) -> dict[str, Any]:
    physical: dict[str, Any] = {"artifactLocation": {"uri": _uri(path)}}
    if line is not None:
        region: dict[str, int] = {"startLine": line}
        if column is not None:
            region["startColumn"] = column
        physical["region"] = region
    return {"physicalLocation": physical}


def _uri(path: Path) -> str:
    """A relative URI when possible, so GitHub can map results to files in the repository."""
    relative = relative_posix(path)
    if Path(relative).is_absolute() or ":" in relative.split("/")[0]:
        return path.resolve().as_uri()
    return quote(relative, safe="/")

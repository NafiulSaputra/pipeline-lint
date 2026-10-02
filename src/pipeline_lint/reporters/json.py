"""JSON output: a stable, machine-readable report."""

from __future__ import annotations

import json
from typing import Any

from pipeline_lint import __version__
from pipeline_lint.engine import LintResult
from pipeline_lint.reporters import relative_posix

JSON_SCHEMA_VERSION = 1


def render_json(result: LintResult) -> str:
    payload: dict[str, Any] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "tool": {"name": "pipeline-lint", "version": __version__},
        "summary": {
            "files_checked": result.files_checked,
            "files_skipped": len(result.skipped),
            "violations": len(result.violations),
            "errors": result.error_count,
            "warnings": result.warning_count,
            "suppressed": result.suppressed,
        },
        "violations": [
            {
                "rule_id": v.rule_id,
                "severity": str(v.severity),
                "path": relative_posix(v.path),
                "line": v.line,
                "column": v.column,
                "message": v.message,
            }
            for v in result.violations
        ],
        "notices": [
            {"path": relative_posix(n.path), "line": n.line, "message": n.message}
            for n in result.notices
        ],
        "skipped": [{"path": relative_posix(s.path), "reason": s.reason} for s in result.skipped],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)

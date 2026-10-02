"""Exceptions raised by pipeline-lint."""

from __future__ import annotations

from pathlib import Path


class PipelineLintError(Exception):
    """Base class for all pipeline-lint errors."""


class SourceError(PipelineLintError):
    """A file could not be read or parsed. The file is skipped, the run continues."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason


class RuleCrashError(PipelineLintError):
    """A rule raised an unexpected exception. This is a bug in pipeline-lint, not in user code."""

    def __init__(self, rule_id: str, path: Path) -> None:
        super().__init__(f"rule {rule_id} crashed while checking {path}")
        self.rule_id = rule_id
        self.path = path


class ConfigError(PipelineLintError):
    """Invalid configuration in pyproject.toml or on the command line."""

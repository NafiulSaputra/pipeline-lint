"""Base class for all rules."""

from __future__ import annotations

from collections.abc import Iterator
from typing import ClassVar

from pipeline_lint.models import Severity, SourceFile, Violation


class Rule:
    """A single lint rule.

    Subclasses set the metadata class variables and override one or more ``check_*`` methods.
    A rule that applies to several languages implements several methods under the same ID,
    so users enable, disable and suppress it as one rule.
    """

    id: ClassVar[str]
    name: ClassVar[str]
    severity: ClassVar[Severity]
    summary: ClassVar[str]
    rationale: ClassVar[str]
    bad_example: ClassVar[str]
    good_example: ClassVar[str]

    def check_python(self, source: SourceFile) -> Iterator[Violation]:
        """Yield violations for a Python file or Databricks notebook. Default: none."""
        return iter(())

    def check_sql(self, source: SourceFile) -> Iterator[Violation]:
        """Yield violations for the SQL statements in a file. Default: none.

        Receives the whole file rather than one statement at a time, because some rules need
        context from earlier statements (for example a DELETE before an INSERT).
        Statements are in ``source.sql_statements``, ordered by line.
        """
        return iter(())

    def violation(self, source: SourceFile, line: int, column: int, message: str) -> Violation:
        """Build a violation carrying this rule's ID and severity."""
        return Violation(
            path=source.path,
            line=line,
            column=column,
            rule_id=self.id,
            severity=self.severity,
            message=message,
        )

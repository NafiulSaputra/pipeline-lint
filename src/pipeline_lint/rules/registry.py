"""Rule registration and selection."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import TypeVar

from pipeline_lint.rules.base import Rule

RULE_ID_PATTERN = re.compile(r"DE\d{3}")

R = TypeVar("R", bound=type[Rule])


class RuleRegistry:
    """Keeps track of rule classes by ID.

    A class (rather than a bare module-level dict) so tests can build an isolated registry
    without touching the global one.
    """

    def __init__(self) -> None:
        self._rules: dict[str, type[Rule]] = {}

    def register(self, rule_cls: R) -> R:
        """Class decorator: add ``rule_cls`` to the registry after validating its ID."""
        rule_id = getattr(rule_cls, "id", None)
        if not isinstance(rule_id, str) or not RULE_ID_PATTERN.fullmatch(rule_id):
            raise ValueError(
                f"{rule_cls.__name__}: rule id must look like 'DE001', got {rule_id!r}"
            )
        existing = self._rules.get(rule_id)
        if existing is not None and existing is not rule_cls:
            raise ValueError(
                f"duplicate rule id {rule_id}: {existing.__name__} and {rule_cls.__name__}"
            )
        self._rules[rule_id] = rule_cls
        return rule_cls

    def rules(self) -> list[Rule]:
        """One instance of every registered rule, sorted by ID."""
        return [cls() for _, cls in sorted(self._rules.items())]


REGISTRY = RuleRegistry()
register = REGISTRY.register


def select_rules(
    rules: Iterable[Rule],
    select: Sequence[str] | None = None,
    ignore: Sequence[str] | None = None,
) -> list[Rule]:
    """Filter rules by ID prefix, like Ruff: ``"DE"`` matches all, ``"DE00"`` matches DE001-DE009.

    ``select=None`` means "all rules". ``ignore`` always wins over ``select``.
    """

    def matches(rule_id: str, patterns: Sequence[str]) -> bool:
        return any(rule_id.startswith(pattern.strip().upper()) for pattern in patterns)

    return [
        rule
        for rule in rules
        if (select is None or matches(rule.id, select))
        and not (ignore and matches(rule.id, ignore))
    ]

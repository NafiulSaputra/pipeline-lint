from __future__ import annotations

import pytest

from pipeline_lint.models import Severity
from pipeline_lint.rules import REGISTRY, Rule, RuleRegistry, select_rules


def make_rule(rule_id: str) -> type[Rule]:
    return type(
        f"Rule{rule_id}",
        (Rule,),
        {
            "id": rule_id,
            "name": "test",
            "severity": Severity.WARNING,
            "summary": "s",
            "rationale": "r",
            "bad_example": "b",
            "good_example": "g",
        },
    )


def test_register_and_list_sorted() -> None:
    registry = RuleRegistry()
    registry.register(make_rule("DE002"))
    registry.register(make_rule("DE001"))
    assert [r.id for r in registry.rules()] == ["DE001", "DE002"]


@pytest.mark.parametrize("bad_id", ["DE1", "XX001", "de001", "DE0010"])
def test_invalid_id_is_rejected(bad_id: str) -> None:
    with pytest.raises(ValueError, match="rule id"):
        RuleRegistry().register(make_rule(bad_id))


def test_duplicate_id_is_rejected() -> None:
    registry = RuleRegistry()
    registry.register(make_rule("DE001"))
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(make_rule("DE001"))


def test_select_and_ignore_by_prefix() -> None:
    registry = RuleRegistry()
    for rule_id in ["DE001", "DE002", "DE010"]:
        registry.register(make_rule(rule_id))
    rules = registry.rules()

    assert [r.id for r in select_rules(rules)] == ["DE001", "DE002", "DE010"]
    assert [r.id for r in select_rules(rules, select=["de00"])] == ["DE001", "DE002"]
    assert [r.id for r in select_rules(rules, ignore=["DE002"])] == ["DE001", "DE010"]
    assert [r.id for r in select_rules(rules, select=["DE"], ignore=["DE0"])] == []


def test_every_builtin_rule_has_complete_metadata() -> None:
    for rule in REGISTRY.rules():
        for attr in ("name", "summary", "rationale", "bad_example", "good_example"):
            assert getattr(rule, attr), f"{rule.id} is missing {attr}"

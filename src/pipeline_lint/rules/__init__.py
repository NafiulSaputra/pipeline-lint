"""Built-in rules. Importing this package registers every rule with :data:`REGISTRY`."""

# Importing a rule module is what registers the rule, so these imports are intentionally unused.
from pipeline_lint.rules import (  # noqa: F401
    de001_non_idempotent_append,
    de002_unscoped_overwrite,
    de003_hardcoded_date,
    de004_select_star_into_write,
    de005_driver_collect,
)
from pipeline_lint.rules.base import Rule
from pipeline_lint.rules.registry import REGISTRY, RuleRegistry, register, select_rules

__all__ = ["REGISTRY", "Rule", "RuleRegistry", "register", "select_rules"]

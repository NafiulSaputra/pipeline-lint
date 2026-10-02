"""Built-in rules. Importing this package registers every rule with :data:`REGISTRY`."""

# Importing a rule module is what registers the rule, so these imports are intentionally unused.
from pipeline_lint.rules import de005_driver_collect  # noqa: F401
from pipeline_lint.rules.base import Rule
from pipeline_lint.rules.registry import REGISTRY, RuleRegistry, register, select_rules

__all__ = ["REGISTRY", "Rule", "RuleRegistry", "register", "select_rules"]

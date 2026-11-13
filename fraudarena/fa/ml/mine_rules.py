"""Owner: M3. baseline_ruleset() -> RuleSet: walk tree leaves with fraud
share >= ml.mine_rules.min_leaf_fraud_share and support >= min_support,
keep each with val FPR <= max_val_fpr; write as v1.

candidates(trace, rs) -> list[dict]: single + pair predicates that stop the
trace's missed_step, ranked by (stops step, lowest added val FPR), each with
evidence. params.yaml ml.mode == "percentile" is the no-ML fallback (99th /
99.5th / 99.9th percentile thresholds on normal traffic).
"""
from __future__ import annotations

from fa.contracts import RuleSet, Trace


def baseline_ruleset() -> RuleSet:
    raise NotImplementedError


def candidates(trace: Trace, rs: RuleSet) -> list[dict]:
    raise NotImplementedError

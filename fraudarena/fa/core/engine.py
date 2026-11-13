"""Owner: M4. The rule engine: decide(state, ev, rs) -> Decision.

A rule fires when ALL its conditions hold (AND). Precedence: block > hold > allow.
`fired` lists the ids of the rules of the winning action (empty for allow).

Call order is always: features = compute_features(state, ev); then
apply(state, ev, action). Both come from M3 (fa.core.features / fa.core.state);
this module never mutates state itself except through apply().

No wall-clock time is used to make decisions; time.perf_counter() only fills
Decision.latency_us for the latency benchmark.
"""
from __future__ import annotations

import operator
import time
from typing import Any, Iterable, Mapping

from fa.contracts import Decision, Rule, RuleSet
from fa.core.features import compute_features
from fa.core.state import apply

_OPS = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
}


def rule_fires(rule: Rule, features: Mapping[str, float]) -> bool:
    """True when every condition of the rule holds. A missing feature never fires."""
    for c in rule.when:
        op = _OPS.get(c.op)
        if op is None:
            raise ValueError(f"unknown operator {c.op!r} in rule {rule.id}")
        val = features.get(c.f)
        if val is None or not op(float(val), float(c.v)):
            return False
    return True


def evaluate(features: Mapping[str, float], rules: Iterable[Rule]) -> tuple[str, list[str]]:
    """Pure decision from a feature dict: (action, ids of the rules that decided)."""
    blocks: list[str] = []
    holds: list[str] = []
    for r in rules:
        if rule_fires(r, features):
            (blocks if r.action == "block" else holds).append(r.id)
    if blocks:
        return "block", blocks
    if holds:
        return "hold", holds
    return "allow", []


def decide_with_features(
    state: Any, ev: Any, rs: RuleSet, *, commit: bool = True
) -> tuple[Decision, dict[str, float]]:
    """Compute features, decide, and (if commit) apply the event to the state.

    Returns the Decision and the feature dict, so callers such as the plan
    executor can keep per-step features for traces.
    """
    t0 = time.perf_counter()
    feats = compute_features(state, ev)
    action, fired = evaluate(feats, rs.rules)
    if commit:
        apply(state, ev, action)
    latency_us = (time.perf_counter() - t0) * 1_000_000
    event_id = ev["event_id"] if isinstance(ev, Mapping) else getattr(ev, "event_id", None)
    if event_id is None and isinstance(ev, Mapping):
        event_id = ev.get("id", "")
    decision = Decision(
        event_id=str(event_id or ""),
        decision=action,  # type: ignore[arg-type]
        fired=fired,
        version=rs.version,
        latency_us=round(latency_us, 2),
    )
    return decision, feats


def decide(state: Any, ev: Any, rs: RuleSet) -> Decision:
    """Decide one event against rule set `rs` and apply it to `state`."""
    return decide_with_features(state, ev, rs, commit=True)[0]


def decide_shadow(state: Any, ev: Any, rs: RuleSet) -> Decision:
    """Decide against `rs` WITHOUT changing the state (candidate-set evaluation)."""
    return decide_with_features(state, ev, rs, commit=False)[0]

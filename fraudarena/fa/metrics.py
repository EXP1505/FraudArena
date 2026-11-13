"""Owner: M3. Metrics: hold rate with Wilson interval, WCEL, normal-traffic friction.

python -m fa.metrics [--seed N] [--split validation|holdout]

hold_rate(decisions) -> (p, lo, hi)     # share held or blocked, 95% Wilson interval
wcel(traces) -> int                     # max loss_through over traces
normal_friction(...)                    # replay a split of normal traffic through a rule set

Uses M4's engine.decide / rules.loader / verify.wilson when they are implemented;
until then falls back to a local evaluator over the plan's baseline R1..R6 so the
friction number can be measured and tuned in parallel.
"""
from __future__ import annotations

import argparse
import math
import operator
from collections import Counter
from typing import Any, Iterable

from fa.contracts import Decision, Trace
from fa.core.state import ev_get

# Phase 1 plan section 6, in the contract's {f, op, v} shape. Placeholder only:
# the real v1 is M4's rules/baseline_v1.json (later mined from data).
STUB_RULES = {"version": "v1-stub", "rules": [
    {"id": "R1", "action": "hold",  "when": [{"f": "amount_ratio_30d", "op": ">=", "v": 10}]},
    {"id": "R2", "action": "hold",  "when": [{"f": "payee_age_h", "op": "<", "v": 1},
                                             {"f": "amount_ratio_30d", "op": ">=", "v": 3}]},
    {"id": "R3", "action": "block", "when": [{"f": "n_pay_1h", "op": ">=", "v": 12}]},
    {"id": "R4", "action": "hold",  "when": [{"f": "device_changed_24h", "op": "==", "v": 1},
                                             {"f": "sum_1h", "op": ">=", "v": 5_000_000}]},
    {"id": "R5", "action": "block", "when": [{"f": "fan_out_1h", "op": ">=", "v": 8}]},
    {"id": "R6", "action": "hold",  "when": [{"f": "night_flag", "op": "==", "v": 1},
                                             {"f": "amount_ratio_30d", "op": ">=", "v": 6}]},
]}

_OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "==": operator.eq}


# ---------------------------------------------------------------- statistics

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    try:
        from fa.verify import wilson as w  # M4
        return w.interval(k, n, z) if hasattr(w, "interval") else w.wilson(k, n, z)
    except Exception:
        pass
    if n == 0:
        return 0.0, 0.0
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def _decision_of(d: Any) -> str:
    if isinstance(d, str):
        return d
    return ev_get(d, "decision") or ev_get(d, "action")


def hold_rate(decisions: Iterable[Decision | str]) -> tuple[float, float, float]:
    """(p, lo, hi): share of decisions that are hold or block, with 95% Wilson interval."""
    n = k = 0
    for d in decisions:
        n += 1
        if _decision_of(d) in ("hold", "block"):
            k += 1
    p = k / n if n else 0.0
    lo, hi = wilson(k, n)
    return p, lo, hi


def wcel(traces: Iterable[Trace]) -> int:
    """Worst-case extractable loss: max loss_through over the traces (0 if none)."""
    return max((int(ev_get(t, "loss_through") or 0) for t in traces), default=0)


# ---------------------------------------------------------------- rule evaluation

def _rules_of(rs: Any) -> list:
    rules = ev_get(rs, "rules", rs)
    return list(rules)


def _cond(c: Any) -> tuple:
    f = ev_get(c, "f") or ev_get(c, "feature")
    v = ev_get(c, "v")
    if v is None:
        v = ev_get(c, "value")
    return f, ev_get(c, "op"), v


def local_decide(features: dict, rs: Any) -> tuple[str, list[str]]:
    """block > hold > allow; returns (decision, fired rule ids)."""
    fired, action = [], "allow"
    for r in _rules_of(rs):
        if all(_OPS[op](features[f], v) for f, op, v in map(_cond, ev_get(r, "when"))):
            fired.append(ev_get(r, "id"))
            a = ev_get(r, "action")
            if a == "block" or (a == "hold" and action == "allow"):
                action = a
    return action, fired


def _ruleset_and_source():
    try:
        from fa.rules import loader  # M4
        return loader.load("v1"), "rules.loader v1"
    except Exception:
        return STUB_RULES, "stub R1..R6 (plan section 6)"


# ---------------------------------------------------------------- friction on normal traffic

def normal_friction(world: dict | None = None, split: str = "validation", rs: Any = None,
                    seed: int | None = None) -> dict:
    """Warm state on history (allow-all), then replay ``split`` through ``rs`` with
    decisions applied. Returns counts, rate and interval over normal payments."""
    from fa.core.features import compute_features
    from fa.core.state import apply
    from fa.world.generator import build_world, warm_state, events_in

    world = world or build_world(seed)
    source = "given"
    if rs is None:
        rs, source = _ruleset_and_source()
    state = warm_state(world)
    labels = world["labels"]

    decisions: list[str] = []
    by_rule, by_tag = Counter(), Counter()
    for ev in events_in(world, split):
        feats = compute_features(state, ev)
        if ev["type"] == "payment":
            d, fired = local_decide(feats, rs)
            decisions.append(d)
            if d != "allow":
                by_rule[fired[0]] += 1
                if ev["event_id"] in labels:
                    by_tag[labels[ev["event_id"]]] += 1
        else:
            d = "allow"
        apply(state, ev, d)

    p, lo, hi = hold_rate(decisions)
    c = Counter(decisions)
    lookalike_pays = Counter(labels[e["event_id"]] for e in events_in(world, split)
                             if e["type"] == "payment" and e["event_id"] in labels)
    return {"rules": source, "seed": world["params"]["seed"], "split": split,
            "payments": len(decisions), "hold": c["hold"], "block": c["block"],
            "rate": p, "lo": lo, "hi": hi, "by_rule": dict(by_rule),
            "flagged_lookalikes": dict(by_tag), "lookalike_payments": dict(lookalike_pays)}


def _print(r: dict) -> None:
    print(f"rules   : {r['rules']}   seed={r['seed']}   split={r['split']}")
    print(f"payments={r['payments']} hold={r['hold']} block={r['block']}  "
          f"hold+block={r['rate']:.3%}  (95% Wilson {r['lo']:.3%} .. {r['hi']:.3%})")
    print(f"by rule : {dict(sorted(r['by_rule'].items()))}")
    print(f"flagged look-alikes {r['flagged_lookalikes']} of {r['lookalike_payments']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--split", default="validation")
    a = ap.parse_args()
    _print(normal_friction(seed=a.seed, split=a.split))

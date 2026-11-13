"""Owner: M3. baseline_ruleset() -> RuleSet: walk tree leaves with fraud
share >= ml.mine_rules.min_leaf_fraud_share and support >= min_support,
keep each with val FPR <= max_val_fpr; write as v1.

candidates(trace, rs) -> list[dict]: single + pair predicates that stop the
trace's missed_step, ranked by (stops loss, lowest added val FPR), each with
evidence. params.yaml ml.mode == "percentile" (or env ML_MODE=percentile) is
the no-ML fallback: single predicates at the 99th / 99.5th / 99.9th percentile
of normal validation traffic.

Candidate dict (consumed by fa.agents.defender):
    conds         list of {f, op, v}      (1..2 conditions, verbatim thresholds)
    action        "hold"
    stopped_loss  paise of loss_through removed when the rule is added (replayed)
    added_fpr_pp  percentage points of extra validation payments flagged vs rs
    evidence      dict (step features, validation counts, threshold source)
"""
from __future__ import annotations

import itertools
import os
from functools import lru_cache

import numpy as np
import pandas as pd

from fa.config import load_config
from fa.contracts import FEATURES, Cond, Rule, RuleSet, Trace
from fa.core.engine import evaluate, rule_fires
from fa.core.features import compute_features
from fa.core.state import apply
from fa.world.generator import build_world, events_in, warm_state

BINARY = ("device_changed_24h", "night_flag")
LOW_IS_RISKY = ("payee_age_h",)
SKIP = ("hour_of_day",)          # night_flag already covers time of day
MONEY = {"pay", "payment", "cashout"}


def _cfg() -> dict:
    return load_config().section("ml")["mine_rules"]


def _mode() -> str:
    return os.environ.get("ML_MODE") or load_config().section("ml").get("mode", "tree")


def _seed() -> int:
    return int(load_config().section("common").get("seed", 42))


# --------------------------------------------------------------- validation traffic

@lru_cache(maxsize=4)
def _validation(seed: int) -> pd.DataFrame:
    """Feature rows of every normal validation payment (state warmed on history, all allowed)."""
    world = build_world(seed)
    state = warm_state(world)
    rows = []
    for ev in events_in(world, "validation"):
        f = compute_features(state, ev)
        if ev["type"] == "payment":
            rows.append(f)
        apply(state, ev, "allow")
    return pd.DataFrame(rows, columns=list(FEATURES))


def _fires(df: pd.DataFrame, conds: list[dict]) -> np.ndarray:
    m = np.ones(len(df), dtype=bool)
    for c in conds:
        col = df[c["f"]].to_numpy()
        m &= {"<": col < c["v"], "<=": col <= c["v"], ">": col > c["v"], ">=": col >= c["v"], "==": col == c["v"]}[c["op"]]
    return m


def _active_flags(df: pd.DataFrame, rs: RuleSet) -> np.ndarray:
    flagged = np.zeros(len(df), dtype=bool)
    for r in rs.rules:
        flagged |= _fires(df, [c.model_dump() for c in r.when])
    return flagged


# --------------------------------------------------------------- baseline v1 (tree)

def _leaf_rules(tree, min_share: float, min_support: int) -> list[dict]:
    t = tree.tree_
    out: list[dict] = []

    def walk(node: int, path: list[dict]) -> None:
        if t.children_left[node] == -1:
            counts = t.value[node][0]
            n = int(t.n_node_samples[node])
            share = float(counts[1] / counts.sum()) if counts.sum() else 0.0   # class-weighted share
            if share >= min_share and n >= min_support:
                out.append({"conds": _merge(path), "support": n, "fraud_share": share})
            return
        f, thr = tree.feature_names_in_[t.feature[node]], float(t.threshold[node])
        walk(t.children_left[node], path + [{"f": f, "op": "<=", "v": thr}])
        walk(t.children_right[node], path + [{"f": f, "op": ">", "v": thr}])

    walk(0, [])
    return out


def _merge(path: list[dict]) -> list[dict]:
    """Keep the tightest bound per (feature, direction): <= keeps the min, > keeps the max."""
    best: dict[tuple, dict] = {}
    for c in path:
        k = (c["f"], c["op"])
        if k not in best or (c["op"] == "<=" and c["v"] < best[k]["v"]) or (c["op"] == ">" and c["v"] > best[k]["v"]):
            best[k] = c
    return [{"f": c["f"], "op": c["op"], "v": round(c["v"], 4)} for c in best.values()]


def baseline_ruleset() -> RuleSet:
    """v1 mined from data: tree leaves that are mostly fraud, kept only if each rule's
    validation FPR stays within max_val_fpr. Percentile mode: one rule per feature."""
    cfg = _cfg()
    val = _validation(_seed())
    rules: list[Rule] = []
    if _mode() == "percentile":
        for f in ("amount_ratio_30d", "sum_1h", "n_pay_1h", "fan_out_1h", "sum_newpayee_1h"):
            q = float(np.quantile(val[f], cfg["percentile_quantiles"][-1]))
            conds = [{"f": f, "op": ">", "v": round(q, 4)}]
            fpr = float(_fires(val, conds).mean())
            if fpr <= cfg["max_val_fpr"]:
                rules.append(_mk_rule(f"P{len(rules) + 1}", conds, "percentile", {"val_fpr": fpr, "quantile": cfg["percentile_quantiles"][-1]}))
        return RuleSet(version="v1", rules=rules)

    from fa.ml.export import load_table
    from fa.ml.split import time_account_split
    from fa.ml.train import train_tree

    sp = time_account_split(load_table(_seed()))
    tree = train_tree(sp["train"], load_config().section("ml")["tree"])
    for leaf in _leaf_rules(tree, cfg["min_leaf_fraud_share"], cfg["min_support"]):
        fpr = float(_fires(val, leaf["conds"]).mean())
        if fpr <= cfg["max_val_fpr"]:
            rules.append(_mk_rule(f"M{len(rules) + 1}", leaf["conds"], "mined",
                                  {"leaf_support": leaf["support"], "leaf_fraud_share": round(leaf["fraud_share"], 4),
                                   "val_fpr": fpr, "val_payments": len(val)}))
    return RuleSet(version="v1", rules=rules)


def _mk_rule(rid: str, conds: list[dict], source: str, evidence: dict) -> Rule:
    return Rule(id=rid, action="hold", when=[Cond(**c) for c in conds[:4]], rationale=f"{source} from data",
                evidence=evidence, source=source, added_in="v1")


# --------------------------------------------------------------- candidates for a missed attack

def _ladder(val: pd.DataFrame, x_row: dict, mode: str, cfg: dict) -> list[tuple[str, dict]]:
    """Single predicates that the missed step satisfies: [(label, cond), ...]."""
    qs = cfg["percentile_quantiles"] if mode == "percentile" else cfg["quantiles"]
    out: list[tuple[str, dict]] = []
    for f in FEATURES:
        x = x_row[f]
        if f in SKIP:
            continue
        if f in BINARY:
            if x == 1 and mode != "percentile":
                out.append(("binary", {"f": f, "op": "==", "v": 1}))
        elif f in LOW_IS_RISKY:
            for h in cfg["lt_ladder_h"]:
                if x < h:
                    out.append((f"<{h}h", {"f": f, "op": "<", "v": float(h)}))
        else:
            seen = set()
            for thr in [0.0] + [round(float(np.quantile(val[f], q)), 4) for q in qs]:  # 0.0 = "any"
                if thr in seen or thr < 0 or thr >= x:
                    continue
                seen.add(thr)
                out.append((f">{thr:g}", {"f": f, "op": ">", "v": thr}))
    return out


def _replay_loss(trace: Trace, rs: RuleSet, rule: Rule) -> int:
    """Loss_through when ``rule`` is added to rs, replaying the trace's own steps."""
    from fa.agents.search import get_plan
    from fa.contracts import Plan
    from fa.world.generator import sandbox_state
    from fa.plans.executor import execute

    plan = get_plan(trace.plan_id) or Plan(plan_id=trace.plan_id, playbook="P1", seed=0,
                                           steps=[s for s, _f, _d in trace.steps])
    patched = RuleSet(version=rs.version, rules=[*rs.rules, rule])
    return execute(plan, sandbox_state(), patched).loss_through


def _stopped_loss(trace: Trace, rs: RuleSet, rule: Rule) -> int:
    if trace.loss_through > 0:
        return trace.loss_through - _replay_loss(trace, rs, rule)
    # no cash-out in the trace (e.g. structuring): count the money steps the rule would flag
    return sum(int(s.amount or 0) for s, f, d in trace.steps
               if s.act in MONEY and d.decision == "allow" and rule_fires(rule, f))


def _target_step(trace: Trace) -> int:
    """Step a rule must flag to stop the loss. The executor counts loss at the allowed
    cash-out, so that is the target when there is one; otherwise the missed step."""
    for i, (s, _f, d) in enumerate(trace.steps):
        if s.act == "cashout" and d.decision == "allow":
            return i
    return trace.missed_step  # type: ignore[return-value]


def candidates(trace: Trace, rs: RuleSet) -> list[dict]:
    if trace.missed_step is None:
        return []
    cfg = _cfg()
    mode = _mode()
    val = _validation(_seed())
    target = _target_step(trace)
    x_row = trace.steps[target][1]
    base_flag = _active_flags(val, rs)
    existing = {tuple(sorted((c.f, c.op, c.v) for c in r.when)) for r in rs.rules}

    singles = _ladder(val, x_row, mode, cfg)
    combos: list[list[dict]] = [[c] for _l, c in singles]
    if mode != "percentile":
        combos += [[a, b] for (_la, a), (_lb, b) in itertools.combinations(singles, 2) if a["f"] != b["f"]]

    scored = []
    for conds in combos:
        key = tuple(sorted((c["f"], c["op"], c["v"]) for c in conds))
        if key in existing:
            continue
        fire = _fires(val, conds)
        added = int((fire & ~base_flag).sum())
        scored.append((added, len(conds), conds))
    scored.sort(key=lambda t: (t[0], t[1]))          # fewest extra validation flags first, then simpler

    out: list[dict] = []
    for i, (added, _n, conds) in enumerate(scored[: int(cfg["top_k_execute"])]):
        rule = Rule(id=f"C{i + 1}", action="hold", when=[Cond(**c) for c in conds],
                    rationale="candidate", source="mined", added_in=rs.version)
        stopped = _stopped_loss(trace, rs, rule)
        if stopped <= 0:
            continue
        out.append({"conds": conds, "action": "hold", "stopped_loss": int(stopped),
                    "added_fpr_pp": 100.0 * added / max(len(val), 1),
                    "evidence": {"missed_step": trace.missed_step, "target_step": target,
                                 "step_features": {k: round(float(v), 4) for k, v in x_row.items()},
                                 "val_payments": len(val), "val_added_flags": added,
                                 "threshold_source": f"{mode}: quantiles of normal validation payments",
                                 "loss_through": trace.loss_through}})
    # Also evaluate pre-mined RBIH tree rules if available
    from pathlib import Path
    for mpath in (Path("data/rbih/current/mined_rules.json"), Path("artifacts/rbih/mined_rules.json")):
        if mpath.exists():
            try:
                import json
                mined_data = json.loads(mpath.read_text(encoding="utf-8"))
                for mr in mined_data:
                    mconds = mr.get("when", [])
                    if not mconds or len(mconds) > 4:
                        continue
                    mkey = tuple(sorted((c["f"], c["op"], c["v"]) for c in mconds))
                    if mkey in existing:
                        continue
                    fire = _fires(val, mconds)
                    added = int((fire & ~base_flag).sum())
                    rule = Rule(
                        id=mr.get("id", "RBM"),
                        action=mr.get("action", "hold"),
                        when=[Cond(**c) for c in mconds],
                        rationale=mr.get("rationale", "Pre-mined rule from RBIH dataset"),
                        evidence=mr.get("evidence", {}),
                        source="mined",
                        added_in=rs.version,
                    )
                    stopped = _stopped_loss(trace, rs, rule)
                    if stopped > 0:
                        out.append({
                            "conds": mconds,
                            "action": mr.get("action", "hold"),
                            "stopped_loss": int(stopped),
                            "added_fpr_pp": 100.0 * added / max(len(val), 1),
                            "evidence": {
                                **mr.get("evidence", {}),
                                "stopped_loss": int(stopped),
                                "source": "RBIH NFPC Phase-2 tree leaf",
                            },
                        })
            except Exception:
                pass
            break

    out.sort(key=lambda c: (-c["stopped_loss"], c["added_fpr_pp"], len(c["conds"])))
    return out

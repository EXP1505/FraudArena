"""Owner: M3. How close is the simulated world to the RBIH data? (docs/PLAN_FINAL_SPLIT follow-up, feature 1)

RBIH rows never leave Kaggle, but `friction_tables.json` records, for each feature and threshold rung,
the share of honest (and mule) transactions at or beyond it. We compute the same share on the simulation
at the same rung and compare point by point:

  honest check   simulated normal payments (validation split)  vs  RBIH honest share
  attack check   simulated attack payments (all playbooks)     vs  RBIH mule share
  rule check     per policy-pack rule: simulated friction      vs  RBIH friction on the test split

Scores use a tolerance written in params.yaml (`fidelity:`), not tuned to look good. Features that RBIH
does not record have no table and are reported as "not measurable". Deterministic for a given world.
"""
from __future__ import annotations

import json
import operator
from pathlib import Path
from typing import Any

import numpy as np

from fa.config import load_config
from fa.contracts import FEATURES, RuleSet

_OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le, "==": operator.eq}
_FT_PATHS = (Path("data/rbih/current/friction_tables.json"), Path("artifacts/rbih/friction_tables.json"))
MONEY = ("payment", "cashout")


def load_real_tables() -> dict | None:
    for p in _FT_PATHS:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))["tables"]
            except Exception:
                continue
    return None


def _cfg() -> dict:
    try:
        return load_config().section("fidelity")
    except Exception:
        return {}


def _share(values: np.ndarray, op: str, thr: float) -> float | None:
    if values.size == 0:
        return None
    return float(100.0 * _OPS[op](values, thr).mean())


# ---------------------------------------------------------------- simulated samples

def honest_samples(world: dict | None = None) -> dict[str, np.ndarray]:
    """Feature values of every payment in the simulated validation split, point-in-time."""
    from fa.core.features import compute_features
    from fa.core.state import apply
    from fa.world.generator import build_world, events_in, warm_state

    w = world or build_world()
    state = warm_state(w)
    cols: dict[str, list[float]] = {f: [] for f in FEATURES}
    for ev in events_in(w, "validation"):
        feats = compute_features(state, ev)
        if ev["type"] in MONEY:
            for f in FEATURES:
                cols[f].append(float(feats.get(f, 0.0)))
        apply(state, ev, "allow")
    return {f: np.asarray(v, dtype=float) for f, v in cols.items()}


def attack_samples(n_per_playbook: int = 40, seed: int = 20260) -> dict[str, np.ndarray]:
    """Feature values of payment/cash-out steps of simulated attacks (no rules, so nothing is stopped)."""
    import random

    from fa.plans.executor import execute
    from fa.plans.playbooks import PARAM_RANGES, build_plan
    from fa.world.generator import sandbox_state

    rng = random.Random(seed)
    empty = RuleSet(version="none", rules=[])
    cols: dict[str, list[float]] = {f: [] for f in FEATURES}
    for pb, ranges in PARAM_RANGES.items():
        for i in range(n_per_playbook):
            params = {k: rng.uniform(lo, hi) for k, (lo, hi) in ranges.items()}
            trace = execute(build_plan(pb, params, seed + i), sandbox_state(), empty)
            for step, feats, _d in trace.steps:
                if step.act in ("pay", "payment", "cashout"):
                    for f in FEATURES:
                        cols[f].append(float(feats.get(f, 0.0)))
    return {f: np.asarray(v, dtype=float) for f, v in cols.items()}


# ---------------------------------------------------------------- comparison

def _band(score: float, cfg: dict) -> str:
    return "close" if score >= cfg.get("close_at", 75) else "drifting" if score >= cfg.get("drifting_at", 50) else "far"


def compare(honest: dict[str, np.ndarray], attacks: dict[str, np.ndarray] | None = None,
            tables: dict | None = None, cfg: dict | None = None) -> dict:
    cfg = cfg or _cfg()
    tol = float(cfg.get("tolerance_pp", 10.0))
    tables = tables if tables is not None else load_real_tables()
    if not tables:
        return {"available": False, "reason": "No RBIH friction tables found. Install the bundle: python -m fa.rbih.install artifacts/rbih"}

    features, scores = [], []
    for f in FEATURES:
        rungs = tables.get(f)
        if not rungs:
            features.append({"feature": f, "measurable": False, "note": "RBIH data has no table for this signal"})
            continue
        rows, gaps, a_gaps = [], [], []
        for r in rungs:
            sim = _share(honest.get(f, np.array([])), r["op"], r["threshold"])
            real = r.get("legit_flagged_pct_test", r.get("legit_flagged_pct_trainval"))
            atk = _share(attacks[f], r["op"], r["threshold"]) if attacks and f in attacks else None
            real_m = r.get("mule_flagged_pct_test", r.get("mule_flagged_pct_trainval"))
            gap = None if sim is None or real is None else abs(sim - real)
            if gap is not None:
                gaps.append(gap)
            a_gap = None if atk is None or real_m is None else atk - real_m
            if a_gap is not None:
                a_gaps.append(a_gap)
            rows.append({"op": r["op"], "threshold": r["threshold"], "real_honest_pct": real, "sim_honest_pct": sim,
                         "gap_pp": gap, "real_mule_pct": real_m, "sim_attack_pct": atk, "attack_minus_mule_pp": a_gap})
        mae = float(np.mean(gaps)) if gaps else None
        score = None if mae is None else round(100.0 * max(0.0, 1.0 - mae / tol), 1)
        if score is not None:
            scores.append(score)
        features.append({"feature": f, "measurable": True, "rungs": rows, "mean_gap_pp": None if mae is None else round(mae, 2),
                         "score": score, "band": None if score is None else _band(score, cfg),
                         "attack_vs_mule_mean_pp": None if not a_gaps else round(float(np.mean(a_gaps)), 2),
                         "attack_note": None if not a_gaps else (
                             "simulated attacks are stronger than real mules here" if np.mean(a_gaps) > tol else
                             "simulated attacks are weaker than real mules here" if np.mean(a_gaps) < -tol else
                             "simulated attacks look like real mules here")})
    overall = round(float(np.mean(scores)), 1) if scores else None
    return {"available": True, "score": overall, "band": None if overall is None else _band(overall, cfg),
            "tolerance_pp": tol, "measured_features": len(scores), "total_features": len(FEATURES), "features": features}


def evidence_threshold(rule: dict, tables: dict | None = None) -> float | None:
    """The threshold RBIH actually measured the rule's evidence at (found by matching the stored test-split
    friction to a rung of the table), or None if it cannot be found."""
    ev = rule.get("evidence") or {}
    feat, real = ev.get("feature"), ev.get("legit_flagged_pct_test")
    tables = tables if tables is not None else load_real_tables()
    if not feat or real is None or not tables or feat not in tables:
        return None
    for r in tables[feat]:
        if abs(float(r.get("legit_flagged_pct_test", -1)) - float(real)) < 1e-9:
            return float(r["threshold"])
    return None


def evidence_matches(rule: dict, tables: dict | None = None) -> bool:
    """True when the rule's own threshold on the evidence feature equals the rung RBIH measured. A rule that
    was tightened after the rung was chosen (for example R6) must not display that rung's numbers."""
    feat = (rule.get("evidence") or {}).get("feature")
    cond = next((c for c in rule.get("when", []) if c["f"] == feat), None)
    thr = evidence_threshold(rule, tables)
    return cond is not None and thr is not None and abs(float(cond["v"]) - thr) < 1e-6 * max(1.0, abs(thr))


def rule_check(honest: dict[str, np.ndarray], rules: list[dict], tables: dict | None = None) -> list[dict]:
    """Per policy-pack rule: friction the simulation predicts for the rule's data-derived condition vs what
    RBIH measured on the test split. Only rules whose threshold is the measured rung are compared."""
    out = []
    for r in rules:
        ev = r.get("evidence") or {}
        feat, real = ev.get("feature"), ev.get("legit_flagged_pct_test")
        cond = next((c for c in r["when"] if c["f"] == feat), None)
        if not feat or real is None or cond is None or feat not in honest:
            out.append({"rule_id": r["id"], "title": r.get("title"), "checked": False,
                        "note": "no RBIH evidence for this rule's signal"})
            continue
        if not evidence_matches(r, tables):
            thr = evidence_threshold(r, tables)
            out.append({"rule_id": r["id"], "title": r.get("title"), "checked": False,
                        "note": f"the rule uses {feat} {cond['op']} {cond['v']:g} but RBIH measured the rung at "
                                f"{'an unknown threshold' if thr is None else f'{thr:g}'}, so the numbers are not comparable"})
            continue
        sim = _share(honest[feat], cond["op"], cond["v"])
        out.append({"rule_id": r["id"], "title": r.get("title"), "checked": True, "feature": feat,
                    "condition": f"{feat} {cond['op']} {cond['v']:g}", "rbih_friction_pct": real, "sim_friction_pct": sim,
                    "gap_pp": None if sim is None else round(sim - real, 3)})
    return out


def report(world: dict | None = None) -> dict:
    """Full fidelity report: comparison + rule check, with the limits stated."""
    from fa.rules.policy_pack import build

    honest = honest_samples(world)
    attacks = attack_samples()
    cmp_ = compare(honest, attacks)
    rules = [r.model_dump(mode="json") for r in build()]
    return {
        **cmp_, "rule_check": rule_check(honest, rules) if cmp_.get("available") else [],
        "samples": {"sim_honest_payments": int(len(next(iter(honest.values())))),
                    "sim_attack_payments": int(len(next(iter(attacks.values()))))},
        "limits": [
            "Only signals that RBIH records can be compared; the rest are marked not measurable.",
            "Matching tail shares shows the distributions are close, not that event sequences are realistic.",
            "RBIH provenance is unconfirmed (it may itself be synthetic): read this as closer to RBIH, not as proof of realism.",
            "Simulated attacks are inspired by mule patterns; RBIH holds mule labels, not the attacks themselves.",
        ],
    }


# ---------------------------------------------------------------- calibration suggestion

def suggest_calibration(grid: dict[str, list[float]] | None = None) -> dict:
    """Try a small grid of generator parameters and report the score of each. Nothing is written: the
    best settings are returned as a params.yaml snippet for a human to apply and commit."""
    import itertools

    from fa.world.generator import build_world, load_params

    cfg = _cfg()
    grid = grid or {k: [float(x) for x in v] for k, v in (cfg.get("calibration_grid") or
                    {"amount_sigma": [0.6, 0.8, 1.0], "new_payee_share": [0.05, 0.15]}).items()}
    tables = load_real_tables()
    if not tables:
        return {"available": False, "reason": "No RBIH friction tables found."}
    base = load_params()
    keys = list(grid)
    trials = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        p = {**base, **dict(zip(keys, combo))}
        s = compare(honest_samples(build_world(params=p)), None, tables, cfg)["score"]
        trials.append({"params": dict(zip(keys, combo)), "score": s})
    current = next((t for t in trials if all(abs(t["params"][k] - float(base.get(k, 0))) < 1e-9 for k in keys)), None)
    best = max(trials, key=lambda t: (t["score"] if t["score"] is not None else -1))
    return {"available": True, "trials": trials, "best": best, "current": current,
            "improves": current is not None and best["score"] is not None and best["score"] > (current["score"] or 0) + 0.5,
            "apply_note": "Nothing was changed. To apply, edit the world: section of params.yaml with these values, "
                          "then run the tests (world_hash will change) and re-measure.",
            "params_yaml": "\n".join(f"  {k}: {v}" for k, v in best["params"].items())}

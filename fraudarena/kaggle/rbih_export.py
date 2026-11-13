"""Write artifacts/rbih/: model, feature spec, friction tables, mined rules, metrics, model card.

Only aggregates and the trained model are exported, never transaction rows: the dataset terms
(reported as CC BY-NC-SA 4.0, unconfirmed) do not allow redistributing it.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from rbih_config import CFG, Config
from rbih_explain import GLOSSARY
from rbih_features import FEATURES

LADDER_Q = (0.5, 0.75, 0.9, 0.95, 0.99, 0.995, 0.999)
LOW_RISKY = ("payee_age_h",)            # rule direction is "<" for these, ">" for the rest
SKIP_LADDER = ("device_changed_24h", "hour_of_day", "night_flag")


def _wq(x: np.ndarray, w: np.ndarray, q: float) -> float:
    o = np.argsort(x)
    c = np.cumsum(w[o]) / w.sum()
    return float(x[o][min(int(np.searchsorted(c, q)), len(x) - 1)])


def friction_tables(df: pd.DataFrame, masks: dict) -> dict:
    """Per feature: threshold ladder derived on train+val legit traffic, measured on train+val and on test.
    Flagged shares of legit are weight-corrected; mule shares are plain (all positives were kept)."""
    dv, te = masks["train"] | masks["val"], masks["test"]
    y, w = df["y"].to_numpy(), df["w"].to_numpy()
    out = {}
    for f in FEATURES:
        if f in SKIP_LADDER:
            continue
        x = df[f].to_numpy()
        neg = dv & (y == 0)
        if neg.sum() == 0:
            continue
        low = f in LOW_RISKY
        qs = [1 - q for q in LADDER_Q] if low else list(LADDER_Q)
        rungs, seen = [], set()
        for q in qs:
            thr = round(_wq(x[neg], w[neg], q), 4)
            if thr in seen:
                continue
            seen.add(thr)
            fire = (lambda a: a < thr) if low else (lambda a: a > thr)
            row = {"op": "<" if low else ">", "threshold": thr}
            for tag, m in (("trainval", dv), ("test", te)):
                legit, mule = m & (y == 0), m & (y == 1)
                row[f"legit_flagged_pct_{tag}"] = float(100 * w[legit & fire(x)].sum() / max(w[legit].sum(), 1e-12))
                row[f"mule_flagged_pct_{tag}"] = float(100 * fire(x[mule]).mean()) if mule.sum() else None
            rungs.append(row)
        out[f] = rungs
    return out


def _merge(path):
    best = {}
    for c in path:
        k = (c["f"], c["op"])
        if k not in best or (c["op"] == "<=" and c["v"] < best[k]["v"]) or (c["op"] == ">" and c["v"] > best[k]["v"]):
            best[k] = c
    return [{"f": c["f"], "op": c["op"], "v": round(float(c["v"]), 4)} for c in best.values()]


def mined_rules(tree, df: pd.DataFrame, masks: dict, min_share=0.5, min_support=50) -> list[dict]:
    """Tree leaves that are mostly mule, in FraudArena Rule shape with test-split evidence."""
    t, te = tree.tree_, masks["test"]
    y, w = df["y"].to_numpy(), df["w"].to_numpy()
    X = df[list(FEATURES)].to_numpy()
    names = list(FEATURES)
    leaves = []

    def walk(node, path):
        if t.children_left[node] == -1:
            counts = t.value[node][0]
            share = float(counts[1] / counts.sum()) if counts.sum() else 0.0
            if share >= min_share and int(t.n_node_samples[node]) >= min_support:
                leaves.append((_merge(path), int(t.n_node_samples[node]), share))
            return
        f, thr = names[t.feature[node]], float(t.threshold[node])
        walk(t.children_left[node], path + [{"f": f, "op": "<=", "v": thr}])
        walk(t.children_right[node], path + [{"f": f, "op": ">", "v": thr}])

    walk(0, [])
    rules = []
    for i, (conds, support, share) in enumerate(leaves, 1):
        fire = np.ones(len(df), bool)
        for c in conds:
            col = X[:, names.index(c["f"])]
            fire &= (col <= c["v"]) if c["op"] == "<=" else (col > c["v"])
        legit, mule = te & (y == 0), te & (y == 1)
        rules.append({
            "id": f"RB{i}", "action": "hold", "when": conds[:4], "source": "mined", "added_in": "v1",
            "rationale": "Mined from the RBIH NFPC Phase-2 mule data (depth-4 tree leaf).",
            "evidence": {"leaf_support": support, "leaf_mule_share_class_weighted": round(share, 4),
                         "test_legit_flagged_pct": float(100 * w[legit & fire].sum() / max(w[legit].sum(), 1e-12)),
                         "test_mule_flagged_pct": float(100 * fire[mule].mean()) if mule.sum() else None,
                         "dataset": "RBIH NFPC Phase-2 (derived)"}})
    return rules


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def export(result: dict, info: dict, ctx: dict, cfg: Config = CFG) -> dict:
    import sklearn
    import xgboost as xgb

    out = cfg.out_dir
    os.makedirs(out, exist_ok=True)
    df, masks = result["df"], result["masks"]
    result["xgboost"].get_booster().save_model(os.path.join(out, "model.json"))
    files = {"model.json": None}

    def dump(name, obj):
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, default=str)
        files[name] = None

    dump("feature_spec.json", {"features": list(FEATURES), "amount_unit": "paise", "windows": "strictly earlier events only",
                               "device_changed_24h": "always 0 (no device field in this dataset)",
                               "receiving_side": "account-centric: the account's own credits (r_fan_in_24h, r_passthrough_1h)",
                               "glossary_features": sorted(GLOSSARY)})
    dump("friction_tables.json", {"note": "aggregates only; thresholds derived on train+val, measured on train+val and test",
                                  "friction_targets": cfg.friction_targets, "tables": friction_tables(df, masks)})
    dump("mined_rules.json", mined_rules(result["tree"], df, masks))
    dump("metrics.json", {"metrics": result["metrics"], "investigate_if_above_0.99": result["investigate_if_above_0.99"]})
    dump("schema_used.json", {"mapping": ctx["mapping"], "warnings": ctx["warnings"], "files": ctx["files"]})

    for name in list(files):
        files[name] = _sha(os.path.join(out, name))
    card = {
        "name": "FraudArena RBIH mule model", "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": "RBIH x IIT Delhi National Fraud Prevention Challenge, Phase 2 (Kaggle). Terms: check the competition page; "
                   "a third party reports CC BY-NC-SA 4.0 (unconfirmed). Non-commercial use only; do not redistribute rows. "
                   "Provenance (synthetic vs real) must be quoted from the Kaggle description.",
        "labels": "account-level is_mule turned into transaction labels: debits within "
                  f"{cfg.mule_window_days} days before the mule flag date are positive; later activity dropped; earlier mule activity: {cfg.mule_outside_window}.",
        "sampling": info, "split": f"by account hash {cfg.train_frac}/{cfg.val_frac}/rest", "seed": cfg.seed,
        "gpu_used": result["gpu_used"], "libraries": {"python": platform.python_version(), "xgboost": xgb.__version__,
                                                       "sklearn": sklearn.__version__, "pandas": pd.__version__},
        "limits": ["No device field: device_changed_24h is 0.", "Labels are account-level; transaction labels are a window rule.",
                   "Attacks are not in this data; FraudArena still simulates them.", "Scores are re-weighted for negative subsampling."],
        "sha256": files}
    dump("model_card.json", card)
    return {"out_dir": out, "files": sorted(files)}

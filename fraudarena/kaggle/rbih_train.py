"""Train the mule detectors (XGBoost on GPU when available + a depth-4 tree for readable rules) and
evaluate them at the operating points a bank cares about: recall at a fixed share of legit
transactions flagged (friction). Negatives were subsampled, so every metric is re-weighted.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from rbih_config import CFG, Config
from rbih_features import FEATURES


def load(con) -> pd.DataFrame:
    return con.execute("SELECT * FROM train").df()


def gpu_ok(cfg: Config) -> bool:
    if cfg.use_gpu == "no":
        return False
    try:
        import xgboost as xgb

        xgb.XGBClassifier(n_estimators=1, device="cuda", tree_method="hist").fit(np.random.rand(20, 3), np.arange(20) % 2)
        return True
    except Exception:
        if cfg.use_gpu == "yes":
            raise
        return False


def weighted_threshold(score_neg: np.ndarray, w_neg: np.ndarray, friction: float) -> float:
    """Smallest threshold such that at most `friction` of legit weight scores >= threshold."""
    order = np.argsort(-score_neg)
    cum = np.cumsum(w_neg[order]) / max(w_neg.sum(), 1e-12)
    k = int(np.searchsorted(cum, friction, side="right"))
    return float(score_neg[order][k]) if k < len(order) else float(score_neg.min() - 1e-9)


def operating_points(y, s, w, thr_from: tuple | None, targets) -> dict:
    """recall / precision / realised friction at thresholds that give `targets` friction on `thr_from`
    (y, s, w of the validation split) or on this split if None."""
    ys, ss, ws = thr_from if thr_from else (y, s, w)
    out = {}
    for f in targets:
        thr = weighted_threshold(ss[ys == 0], ws[ys == 0], f)
        hit = s >= thr
        pos_w, neg_w = w[y == 1].sum(), w[y == 0].sum()
        tp, fp = w[(y == 1) & hit].sum(), w[(y == 0) & hit].sum()
        out[f"{f:.3%}"] = {"threshold": thr, "recall": float(tp / max(pos_w, 1e-12)),
                           "precision": float(tp / max(tp + fp, 1e-12)), "friction_realised": float(fp / max(neg_w, 1e-12))}
    return out


def evaluate(df: pd.DataFrame, score: np.ndarray, cfg: Config, val_mask, test_mask) -> dict:
    from sklearn.metrics import average_precision_score, roc_auc_score

    y, w = df["y"].to_numpy(), df["w"].to_numpy()
    res = {}
    for name, m in (("val", val_mask), ("test", test_mask)):
        if m.sum() == 0 or len(np.unique(y[m])) < 2:
            res[name] = {"note": "needs both classes"}
            continue
        thr_from = (y[val_mask], score[val_mask], w[val_mask]) if name == "test" else None
        res[name] = {
            "rows": int(m.sum()), "positives": int((y[m] == 1).sum()),
            "pr_auc_weighted": float(average_precision_score(y[m], score[m], sample_weight=w[m])),
            "roc_auc_weighted": float(roc_auc_score(y[m], score[m], sample_weight=w[m])),
            "at_friction": operating_points(y[m], score[m], w[m], thr_from, cfg.friction_targets),
            "threshold_chosen_on": "val" if name == "test" else "this split",
        }
        reason = df["reason"].to_numpy()
        per = {}
        if name == "test" and "at_friction" in res[name]:
            thr = list(res[name]["at_friction"].values())[min(1, len(cfg.friction_targets) - 1)]["threshold"]
            for r in pd.unique(reason[m & (y == 1)]):
                if r is None or (isinstance(r, float) and np.isnan(r)):
                    continue
                mm = m & (y == 1) & (reason == r)
                per[str(r)] = {"rows": int(mm.sum()), "recall": float((score[mm] >= thr).mean())}
        if per:
            res[name]["recall_by_alert_reason_at_middle_friction"] = per
    return res


def train_all(cfg: Config = CFG, con=None, df: pd.DataFrame | None = None) -> dict:
    import xgboost as xgb
    from sklearn.tree import DecisionTreeClassifier

    df = load(con) if df is None else df
    X, y = df[list(FEATURES)], df["y"].to_numpy()
    tr, va, te = (df["split"] == "train").to_numpy(), (df["split"] == "val").to_numpy(), (df["split"] == "test").to_numpy()
    if len(np.unique(y[tr])) < 2:
        raise RuntimeError("Training split has a single class: raise CFG.legit_account_frac or check the labelling window.")
    spw = float((y[tr] == 0).sum() / max((y[tr] == 1).sum(), 1))
    gpu = gpu_ok(cfg)
    clf = xgb.XGBClassifier(n_estimators=400, max_depth=5, learning_rate=0.08, subsample=0.8, colsample_bytree=0.8,
                            min_child_weight=3, scale_pos_weight=min(spw, 50.0), random_state=cfg.seed, n_jobs=cfg.threads,
                            tree_method="hist", device="cuda" if gpu else "cpu", eval_metric="aucpr",
                            early_stopping_rounds=30 if va.sum() and len(np.unique(y[va])) > 1 else None)
    if clf.early_stopping_rounds:
        clf.fit(X[tr], y[tr], eval_set=[(X[va], y[va])], verbose=False)
    else:
        clf.fit(X[tr], y[tr], verbose=False)
    s_xgb = clf.predict_proba(X)[:, 1]

    tree = DecisionTreeClassifier(max_depth=4, min_samples_leaf=max(50, int(0.0005 * tr.sum())), class_weight="balanced",
                                  random_state=cfg.seed).fit(X[tr], y[tr])
    s_tree = tree.predict_proba(X)[:, 1]

    metrics = {"xgboost": evaluate(df, s_xgb, cfg, va, te), "decision_tree": evaluate(df, s_tree, cfg, va, te)}
    suspicious = [f"{m}/{sp}/{k}={v:.3f}" for m, d in metrics.items() for sp, r in d.items() if isinstance(r, dict)
                  for k, v in r.items() if k in ("pr_auc_weighted", "roc_auc_weighted") and v > 0.99]
    return {"xgboost": clf, "tree": tree, "df": df, "scores": {"xgboost": s_xgb, "tree": s_tree}, "metrics": metrics,
            "masks": {"train": tr, "val": va, "test": te}, "gpu_used": gpu,
            "investigate_if_above_0.99": suspicious}

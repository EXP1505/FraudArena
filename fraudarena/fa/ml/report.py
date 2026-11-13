"""Owner: M3. precision, recall, FPR, PR-AUC, P@100 per split -> a results
table (markdown + JSON). Anything above 0.99 is investigated as a leakage bug.

python -m fa.ml.report   # export (cached), train tree + xgboost, write data/ml/results.{json,md}
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fa.ml.split import feature_matrix, labels

FLAG_ABOVE = 0.99


def report(model, splits: dict[str, pd.DataFrame]) -> dict:
    from sklearn.metrics import average_precision_score

    out: dict = {}
    for name, df in splits.items():
        if len(df) == 0:
            continue
        X, y = feature_matrix(df), labels(df).to_numpy()
        s = model.predict_proba(X)[:, 1]
        pred = (s >= 0.5).astype(int)
        tp = int(((pred == 1) & (y == 1)).sum())
        fp = int(((pred == 1) & (y == 0)).sum())
        fn = int(((pred == 0) & (y == 1)).sum())
        tn = int(((pred == 0) & (y == 0)).sum())
        top = np.argsort(-s, kind="stable")[:100]
        m = {"n": int(len(y)), "positives": int(y.sum()),
             "precision": tp / (tp + fp) if tp + fp else 0.0,
             "recall": tp / (tp + fn) if tp + fn else 0.0,
             "fpr": fp / (fp + tn) if fp + tn else 0.0,
             "pr_auc": float(average_precision_score(y, s)) if y.sum() else 0.0,
             "p_at_100": float(y[top].mean())}
        if y.sum() == len(y):   # positives only: precision / PR-AUC / P@100 are meaningless, recall is the number
            m["precision"] = m["pr_auc"] = m["p_at_100"] = None
        m["investigate"] = sorted(k for k in ("precision", "recall", "pr_auc", "p_at_100") if m[k] is not None and m[k] > FLAG_ABOVE)
        out[name] = m
    return out


def to_markdown(results: dict) -> str:
    lines = ["| experiment | model | split | n | precision | recall | FPR | PR-AUC | P@100 | >0.99 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for exp, models in results.items():
        for model, splits in models.items():
            for split, m in splits.items():
                f3 = lambda v, d=3: "n/a" if v is None else f"{v:.{d}f}"  # noqa: E731
                lines.append(f"| {exp} | {model} | {split} | {m['n']} | {f3(m['precision'])} | {m['recall']:.3f} | "
                             f"{m['fpr']:.4f} | {f3(m['pr_auc'])} | {f3(m['p_at_100'], 2)} | "
                             f"{', '.join(m['investigate']) or '-'} |")
    return "\n".join(lines) + "\n"


MODEL_FILES = {"tree": "decision_tree", "xgboost": "xgboost"}


def table_sha256(path: Path) -> str:
    """Fingerprint of the table's CONTENT (column names + every value), not of the file's bytes.
    A parquet file's bytes change with the pyarrow/pandas version, so hashing the file made the
    fingerprint differ between machines for identical data."""
    import hashlib

    import pandas as pd

    df = pd.read_parquet(path)
    h = hashlib.sha256()
    h.update("|".join(map(str, df.columns)).encode("utf-8"))
    h.update(pd.util.hash_pandas_object(df, index=False).to_numpy().tobytes())
    return h.hexdigest()


def save_models(models: dict, results: dict, table_path: Path, n_rows: int, seed: int, out_dir: Path) -> None:
    """Persist each trained model (joblib) with a JSON model card, plus the tree as readable text."""
    import joblib
    from datetime import datetime, timezone
    from sklearn.tree import export_text

    from fa.contracts import FEATURES

    mdir = out_dir / "models"
    mdir.mkdir(parents=True, exist_ok=True)
    for key, fname in MODEL_FILES.items():
        joblib.dump(models[key], mdir / f"{fname}.joblib")
        card = {"model": fname, "seed": seed, "split_names": ["train", "val", "test"],
                "features": list(FEATURES),
                "metrics": {exp: splits[key] for exp, splits in results.items()},
                "training_table": {"path": str(table_path).replace("\\", "/"), "rows": n_rows, "sha256": table_sha256(table_path)},
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        (mdir / f"{fname}.card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    (mdir / "decision_tree_leaves.txt").write_text(
        export_text(models["tree"], feature_names=list(FEATURES)), encoding="utf-8")


def run_all(seed: int | None = None, out_dir: Path = Path("data/ml"), refresh: bool = False) -> dict:
    """Train + evaluate. Models are a comparison / rule-mining aid only: the tree's leaves become JSON
    rules via fa.ml.mine_rules; no live component (attacker, defender, gates) calls a model."""
    from fa.config import load_config
    from fa.ml.export import load_table
    from fa.ml.split import leave_one_playbook_out, time_account_split
    from fa.ml.train import train_tree, train_xgboost

    cfg = load_config()
    ml = cfg.section("ml")
    seed = int(cfg.section("common").get("seed", 42) if seed is None else seed)
    table_path = Path(f"data/ml/training_table_s{seed}.parquet")
    df = load_table(seed, path=table_path, refresh=refresh)
    results: dict = {}

    def both(train_df, evals):
        tree, xgb = train_tree(train_df, ml["tree"]), train_xgboost(train_df, ml["xgboost"])
        return {"tree": report(tree, evals), "xgboost": report(xgb, evals)}, {"tree": tree, "xgboost": xgb}

    sp = time_account_split(df)
    results["time+account split"], main_models = both(sp["train"], {"val": sp["val"], "test": sp["test"]})
    for pb in sorted(set(df.loc[df["playbook"] != "", "playbook"])):
        lo = leave_one_playbook_out(df, pb)
        results[f"leave out {pb}"], _ = both(lo["train"], {"test": lo["test"], "heldout_attacks": lo["heldout_attacks"]})

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (out_dir / "results.md").write_text(to_markdown(results), encoding="utf-8")
    save_models(main_models, results, table_path, len(df), seed, out_dir)
    return results


if __name__ == "__main__":
    import sys
    print(to_markdown(run_all(refresh="--refresh" in sys.argv)))

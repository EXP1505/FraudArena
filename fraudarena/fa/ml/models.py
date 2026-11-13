"""Owner: M3. Load a model saved by `python -m fa.ml.report` together with its model card."""
from __future__ import annotations

import json
from pathlib import Path

MODEL_DIR = Path("data/ml/models")
NAMES = ("decision_tree", "xgboost")


def load_model(name: str, model_dir: Path | None = None):
    """Return (model, card) for ``name`` ("decision_tree" | "xgboost")."""
    import joblib

    if name not in NAMES:
        raise ValueError(f"unknown model {name!r}; expected one of {NAMES}")
    d = Path(model_dir or MODEL_DIR)
    mp, cp = d / f"{name}.joblib", d / f"{name}.card.json"
    if not mp.exists() or not cp.exists():
        raise FileNotFoundError(f"model {name!r} not found in {d}. Run `python -m fa.ml.report` to train and save it.")
    return joblib.load(mp), json.loads(cp.read_text(encoding="utf-8"))

"""Owner: M3 (Person A). Transaction scorer using trained XGBoost model (docs/PLAN_IMPLEMENTATION.pdf M3-D).

Loads model.json from data/rbih/current/ and computes fraud score + top-3 plain-language
reasons using xgboost pred_contribs. Returns None or available=False when no model is installed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from fa.contracts import FEATURES
from fa.rules.explain import FEATURE_GLOSSARY

MODEL_PATH = Path("data/rbih/current/model.json")
FALLBACK_MODEL_PATH = Path("artifacts/rbih/model.json")


class Scorer:
    def __init__(self, model_path: Path | str | None = None) -> None:
        self.booster = None
        self.feature_names = list(FEATURES)

        candidates = [Path(model_path)] if model_path else [MODEL_PATH, FALLBACK_MODEL_PATH]
        for p in candidates:
            if p and p.exists():
                try:
                    import xgboost as xgb

                    b = xgb.Booster()
                    b.load_model(str(p))
                    self.booster = b
                    self.model_path = p
                    break
                except Exception:
                    pass

    @property
    def is_available(self) -> bool:
        return self.booster is not None

    def score(self, features: dict[str, float | int | bool], top_reasons: int = 3) -> dict[str, Any]:
        """Score a single transaction's feature dictionary.
        Returns: {"available": bool, "score": float, "reasons": [{"feature", "push", "text"}]}
        """
        if not self.is_available:
            return {"available": False, "score": 0.0, "reasons": []}

        import pandas as pd
        import xgboost as xgb

        row_data = {f: float(features.get(f, 0.0)) for f in self.feature_names}
        df = pd.DataFrame([row_data])
        dmat = xgb.DMatrix(df[self.feature_names], feature_names=self.feature_names)

        prob = float(self.booster.predict(dmat)[0])

        # Compute SHAP / tree feature push contributions
        reasons_list = []
        try:
            contribs = self.booster.predict(dmat, pred_contribs=True)[0]
            feature_contribs = dict(zip(self.feature_names, contribs[:-1]))

            # Filter positive push and sort descending
            ranked = sorted(
                ((f, c) for f, c in feature_contribs.items() if c > 0.02 and f != "device_changed_24h"),
                key=lambda t: -t[1],
            )
            for f, push in ranked[:top_reasons]:
                v = row_data[f]
                explain_fn = FEATURE_GLOSSARY.get(f)
                text = f"Payment {explain_fn('>=', v)}" if explain_fn else f"{f} elevated"
                reasons_list.append({
                    "feature": f,
                    "push": round(float(push), 4),
                    "text": text,
                })
        except Exception:
            pass

        return {
            "available": True,
            "score": round(prob, 4),
            "reasons": reasons_list,
        }


_DEFAULT_SCORER: Scorer | None = None


def get_default_scorer() -> Scorer:
    global _DEFAULT_SCORER
    if _DEFAULT_SCORER is None:
        _DEFAULT_SCORER = Scorer()
    return _DEFAULT_SCORER


def score_transaction(features: dict[str, Any]) -> dict[str, Any]:
    """Helper for Person B and api routes to score features directly."""
    return get_default_scorer().score(features)

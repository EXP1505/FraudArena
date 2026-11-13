"""Plain-language reasons for a model score.

xgboost's own `pred_contribs=True` gives each feature's push towards "mule" (no extra library). The top
positive contributors are turned into sentences by the glossary below (kept in sync by hand with
fa/rules/explain.py in the FraudArena repo; this folder must stay self-contained for Kaggle).
"""
from __future__ import annotations


def _rupees(paise: float) -> str:
    return f"₹{paise / 100:,.0f}"


def _hour(h: float) -> str:
    h = int(h)
    return f"{(h % 12) or 12}{'am' if h < 12 else 'pm'}"


GLOSSARY = {
    "amount_ratio_30d": lambda v: f"the payment is {v:.1f}x larger than this account's usual payment",
    "payee_age_h": lambda v: "the payee is brand new" if v < 1 else f"the payee was first used only {v:.0f} hours ago",
    "n_pay_1h": lambda v: f"{int(v)} payments were made in the last hour",
    "n_pay_24h": lambda v: f"{int(v)} payments were made in the last 24 hours",
    "sum_1h": lambda v: f"{_rupees(v)} was paid out in the last hour",
    "sum_24h": lambda v: f"{_rupees(v)} was paid out in the last 24 hours",
    "sum_newpayee_1h": lambda v: f"{_rupees(v)} went to brand-new payees in the last hour",
    "fan_out_1h": lambda v: f"money was sent to {int(v)} different people in the last hour",
    "r_fan_in_24h": lambda v: f"{int(v)} different senders paid into this account in the last 24 hours",
    "r_passthrough_1h": lambda v: f"{v * 100:.0f}% of the money received in the last hour has already left",
    "hour_of_day": lambda v: f"the payment was made at {_hour(v)}",
    "night_flag": lambda v: "the payment was made at night (before 5am)",
}
NEUTRAL = ("device_changed_24h",)       # constant in this dataset, never shown as a reason


def reasons(contribs: dict[str, float], values: dict[str, float], top: int = 3, min_push: float = 0.05) -> list[dict]:
    """Top features pushing the score towards 'mule', as [{feature, push, text}]."""
    ranked = sorted(((f, c) for f, c in contribs.items() if c > min_push and f not in NEUTRAL), key=lambda t: -t[1])
    out = []
    for f, c in ranked[:top]:
        text = GLOSSARY.get(f, lambda v: f"{f} = {v:.3g}")(values[f])
        out.append({"feature": f, "push": round(float(c), 4), "text": text[0].upper() + text[1:]})
    return out


def explain_rows(booster, X, feature_names: list[str], top: int = 3):
    """Reasons for every row of a DataFrame X (columns = feature_names) using xgboost pred_contribs."""
    import xgboost as xgb

    d = xgb.DMatrix(X[feature_names], feature_names=feature_names)
    contrib = booster.predict(d, pred_contribs=True)       # last column is the bias term
    return [reasons(dict(zip(feature_names, row[:-1])), dict(zip(feature_names, X[feature_names].iloc[i])), top)
            for i, row in enumerate(contrib)]

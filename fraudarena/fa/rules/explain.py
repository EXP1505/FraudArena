"""Owner: M4 (Person A). Plain-language rule explainer (docs/PLAN_IMPLEMENTATION.pdf M4-A).

Generates plain titles, customer messages, analyst notes, and treatment
descriptions without leaking raw feature names or internal variable codes.
"""
from __future__ import annotations

import re
from typing import Any

from fa.contracts import Rule


def _rupees(paise: float | int) -> str:
    return f"₹{float(paise) / 100:,.0f}"


def _hour(h: float | int) -> str:
    h = int(h)
    return f"{(h % 12) or 12}{'am' if h < 12 else 'pm'}"


FEATURE_GLOSSARY = {
    "amount_ratio_30d": lambda op, v: f"is {v:.1f}× larger than your average spending over the last 30 days",
    "payee_age_h": lambda op, v: "was added to your account less than an hour ago" if v <= 1 else f"was added {v:.0f} hours ago",
    "device_changed_24h": lambda op, v: "came from a new phone or unverified device",
    "n_pay_1h": lambda op, v: f"follows {int(v)} or more rapid payments made in the last hour",
    "n_pay_24h": lambda op, v: f"follows {int(v)} or more payments made in the last 24 hours",
    "sum_1h": lambda op, v: f"exceeds {_rupees(v)} paid out in the last hour",
    "sum_24h": lambda op, v: f"exceeds {_rupees(v)} paid out in the last 24 hours",
    "sum_newpayee_1h": lambda op, v: f"exceeds {_rupees(v)} sent to newly linked payees in the last hour",
    "fan_out_1h": lambda op, v: f"is part of a burst sending money to {int(v)} different recipients in an hour",
    "r_fan_in_24h": lambda op, v: f"involves an account receiving incoming funds from {int(v)} different people in 24 hours",
    "r_passthrough_1h": lambda op, v: f"involves funds being routed straight out ({v * 100:.0f}% outflow ratio)",
    "hour_of_day": lambda op, v: f"was initiated at unusual off-hours ({_hour(v)})",
    "night_flag": lambda op, v: "was attempted late at night (between midnight and 5am)",
}

# Known titles & customer messages for canonical rules
CANONICAL_TEXTS = {
    "R1": {
        "title": "Much larger than usual",
        "customer_message": "This payment is much larger than your usual payments, so we paused it to check it is you.",
        "treatment": "Hold + step-up authentication",
    },
    "R2": {
        "title": "New payee, big amount",
        "customer_message": "You added this person very recently and the amount is large. Please confirm it is really them.",
        "treatment": "Hold + confirmation or callback",
    },
    "R3": {
        "title": "Too many payments in an hour",
        "customer_message": "We saw an unusual burst of payments and stopped it for your safety.",
        "treatment": "Block",
    },
    "R4": {
        "title": "New phone, money moving",
        "customer_message": "This payment came from a phone we have not seen before.",
        "treatment": "Hold + step-up authentication",
    },
    "R5": {
        "title": "Paying many different people quickly",
        "customer_message": "Money was sent to many different people in a short time.",
        "treatment": "Block",
    },
    "R6": {
        "title": "Large payment at night",
        "customer_message": "A large payment was attempted late at night.",
        "treatment": "Hold + step-up authentication",
    },
    "R7": {
        "title": "Money passes straight through",
        "customer_message": "This account receives from many senders and sends the money straight out.",
        "treatment": "Hold + review",
    },
}


def explain(rule: Rule | dict[str, Any]) -> dict[str, str]:
    """Return {title, customer_message, analyst_note, treatment} for any rule."""
    r_id = getattr(rule, "id", None) or (rule.get("id") if isinstance(rule, dict) else "")
    action = getattr(rule, "action", None) or (rule.get("action") if isinstance(rule, dict) else "hold")
    conds = getattr(rule, "when", None) or (rule.get("when") if isinstance(rule, dict) else [])

    if r_id in CANONICAL_TEXTS:
        known = CANONICAL_TEXTS[r_id]
        analyst_parts = []
        for c in conds:
            f = getattr(c, "f", None) or c.get("f")
            v = getattr(c, "v", None) if getattr(c, "v", None) is not None else c.get("v")
            op = getattr(c, "op", None) or c.get("op")
            phrase = FEATURE_GLOSSARY.get(f, lambda o, val: f"{f} {o} {val}")(op, v)
            analyst_parts.append(phrase)

        return {
            "title": known["title"],
            "customer_message": known["customer_message"],
            "analyst_note": f"Fires when payment {', and '.join(analyst_parts)}.",
            "treatment": known["treatment"],
        }

    # For mined or dynamic rules (e.g. RB1-RB11 or LLM-proposed defender patches)
    phrases = []
    for c in conds:
        f = getattr(c, "f", None) or c.get("f")
        v = getattr(c, "v", None) if getattr(c, "v", None) is not None else c.get("v")
        op = getattr(c, "op", None) or c.get("op")
        phrase = FEATURE_GLOSSARY.get(f, lambda o, val: f"{f} {o} {val}")(op, v)
        phrases.append(phrase)

    combined = ", and ".join(phrases) if phrases else "triggers abnormal risk indicators"
    title = f"Risk Pattern {r_id}" if r_id else "Unusual Activity Pattern"
    if "night" in combined:
        title = "Late Night Activity"
    elif "different people" in combined:
        title = "Rapid Multi-Payee Scatter"
    elif "outflow ratio" in combined or "senders" in combined:
        title = "Pass-Through Funnel"
    elif "rapid payments" in combined:
        title = "High Velocity Burst"

    treatment = "Block payment" if action == "block" else "Hold + step-up authentication"
    customer_message = f"We noticed this payment {combined}. We paused it for your protection."
    analyst_note = f"Automated defense rule firing when payment {combined}."

    return {
        "title": title,
        "customer_message": customer_message,
        "analyst_note": analyst_note,
        "treatment": treatment,
    }

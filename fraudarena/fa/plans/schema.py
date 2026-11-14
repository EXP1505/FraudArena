"""Owner: M1. JSON-schema caps for an attack Plan (24h plan section 4.2).

Caps: sandbox roles only (victim|mule), <=12 steps, <=72h horizon, total
amount moved <=200x the victim's mean payment. Enforced by fa.plans.validator.
"""
from __future__ import annotations

MAX_STEPS = 12
MAX_SPAN_HOURS = 72
MAX_SPAN_SECONDS = MAX_SPAN_HOURS * 3600
MAX_TOTAL_VS_VICTIM_MEAN = 200
SANDBOX_ACTORS = frozenset({"victim", "mule"})
ALLOWED_ACTS = frozenset({"login", "add_payee", "pay", "payment", "cashout"})


def plan_schema() -> dict:
    """Return the JSON schema a Plan dict must satisfy before validate()."""
    return {
        "type": "object",
        "required": ["plan_id", "playbook", "seed", "params", "steps"],
        "properties": {
            "plan_id": {"type": "string"},
            "playbook": {"type": "string", "pattern": r"^(P[1-3]|X-[0-9a-f]{4,12})$"},
            "seed": {"type": "integer"},
            "params": {"type": "object"},
            "steps": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_STEPS,
                "items": {
                    "type": "object",
                    "required": ["t", "actor", "act"],
                    "properties": {
                        "t": {"type": "integer", "minimum": 0},
                        "actor": {"enum": sorted(SANDBOX_ACTORS)},
                        "act": {"enum": sorted(ALLOWED_ACTS)},
                        "payee": {"type": ["string", "null"]},
                        "device": {"type": ["string", "null"]},
                        "amount": {"type": ["integer", "null"], "minimum": 0},
                    },
                },
            },
        },
    }

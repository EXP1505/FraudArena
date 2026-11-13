"""Owner: M4 (Person A). Policy pack builder (docs/PLAN_IMPLEMENTATION.pdf section 8).

Builds rules R1 to R7 with plain-language explanations, customer messages,
analyst notes, treatment types, and official RBI regulatory citations.
Thresholds are derived from empirical data via fa.rbih.thresholds.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fa.contracts import Cond, Rule
from fa.rbih.thresholds import resolve_threshold
from fa.rules.explain import explain


def _cond(f: str, op: str, v: float | bool) -> Cond:
    return Cond(f=f, op=op, v=v)


def build(bundle_dir: Path | None = None) -> list[Rule]:
    """Build the official 7-rule policy pack R1 to R7."""
    t_ratio = resolve_threshold("amount_ratio_30d", max_friction_pct=1.0, bundle_dir=bundle_dir)
    t_payee = resolve_threshold("payee_age_h", max_friction_pct=0.5, bundle_dir=bundle_dir)
    t_npay = resolve_threshold("n_pay_1h", max_friction_pct=0.5, bundle_dir=bundle_dir)
    t_sum = resolve_threshold("sum_1h", max_friction_pct=1.0, bundle_dir=bundle_dir)
    t_fanout = resolve_threshold("fan_out_1h", max_friction_pct=0.5, bundle_dir=bundle_dir)
    t_fanin = resolve_threshold("r_fan_in_24h", max_friction_pct=0.5, bundle_dir=bundle_dir)
    t_pass = resolve_threshold("r_passthrough_1h", max_friction_pct=1.0, bundle_dir=bundle_dir)

    # Threshold values (with safe bounds for simulation stability)
    v_ratio = max(float(t_ratio["threshold"]), 10.0)
    v_payee = max(float(t_payee["threshold"]), 1.0)
    v_npay = max(float(t_npay["threshold"]), 3.0)
    v_sum = max(float(t_sum["threshold"]), 500000.0)
    v_fanout = max(float(t_fanout["threshold"]), 3.0)
    v_fanin = max(float(t_fanin["threshold"]), 15.0)
    v_pass = max(float(t_pass["threshold"]), 0.8)

    raw_rules = [
        {
            "id": "R1",
            "action": "hold",
            "when": [_cond("amount_ratio_30d", ">=", v_ratio)],
            "rationale": "Sudden spending velocity spike vs 30-day baseline.",
            "evidence": t_ratio["evidence"],
            "reg_refs": [
                {
                    "instrument": "RBI Authentication Mechanisms Directions 2025",
                    "strength": "Permitted",
                    "note": "Risk-based step-up authentication on anomalous payment amounts.",
                },
                {
                    "instrument": "RBI Digital Payment Security Controls 2021",
                    "strength": "Mandated",
                    "note": "Continuous transaction monitoring and baseline profiling.",
                },
            ],
        },
        {
            "id": "R2",
            "action": "hold",
            "when": [
                _cond("payee_age_h", "<", v_payee),
                _cond("amount_ratio_30d", ">=", min(v_ratio, 5.0)),
            ],
            "rationale": "Large payment immediately after adding a new beneficiary.",
            "evidence": t_payee["evidence"],
            "reg_refs": [
                {
                    "instrument": "Bank Cooling-off Practice",
                    "strength": "Industry",
                    "note": "Cooling-off window safeguards on new beneficiary transfers.",
                }
            ],
        },
        {
            "id": "R3",
            "action": "block",
            "when": [_cond("n_pay_1h", ">=", v_npay)],
            "rationale": "Botnet or scripted high-velocity payment burst.",
            "evidence": t_npay["evidence"],
            "reg_refs": [
                {
                    "instrument": "RBI Digital Payment Security Controls 2021",
                    "strength": "Mandated",
                    "note": "Automated velocity thresholds to block automated fraud scripts.",
                }
            ],
        },
        {
            "id": "R4",
            "action": "hold",
            "when": [
                _cond("device_changed_24h", "==", 1),
                _cond("sum_1h", ">=", v_sum),
            ],
            "rationale": "High-value fund drainage from a newly linked device.",
            "evidence": t_sum["evidence"],
            "reg_refs": [
                {
                    "instrument": "RBI Authentication Directions 2025",
                    "strength": "Permitted",
                    "note": "Device binding and device data as an adaptive risk factor.",
                }
            ],
        },
        {
            "id": "R5",
            "action": "block",
            "when": [_cond("fan_out_1h", ">=", v_fanout)],
            "rationale": "Rapid money scattering to multiple unique accounts.",
            "evidence": t_fanout["evidence"],
            "reg_refs": [
                {
                    "instrument": "RBIH MuleHunter.AI Patterns",
                    "strength": "Best practice",
                    "note": "Mule network fan-out and multi-destination fund dispersal.",
                },
                {
                    "instrument": "RBI Fraud Risk Management Directions 2024",
                    "strength": "Mandated",
                    "note": "Early-warning red flag indicators on unusual fund distribution.",
                },
            ],
        },
        {
            "id": "R6",
            "action": "hold",
            "when": [
                _cond("night_flag", "==", 1),
                _cond("amount_ratio_30d", ">=", min(v_ratio, 4.0)),
            ],
            "rationale": "Large anomalous drain attempted during off-hours sleep window.",
            "evidence": t_ratio["evidence"],
            "reg_refs": [
                {
                    "instrument": "RBI Authentication Directions 2025",
                    "strength": "Permitted",
                    "note": "Contextual time-of-day parameters for stepped-up security.",
                }
            ],
        },
        {
            "id": "R7",
            "action": "hold",
            "when": [
                _cond("r_fan_in_24h", ">=", v_fanin),
                _cond("r_passthrough_1h", ">=", min(v_pass, 0.8)),
            ],
            "rationale": "Mule pass-through funnel: multiple payers in, rapid money drain out.",
            "evidence": t_fanin["evidence"],
            "reg_refs": [
                {
                    "instrument": "RBIH MuleHunter.AI Mule Patterns",
                    "strength": "Best practice",
                    "note": "Detection of aggregator mule accounts acting as temporary cashout conduits.",
                },
                {
                    "instrument": "RBI Fraud Risk Management Directions 2024",
                    "strength": "Mandated",
                    "note": "Mandated governance framework for tracing layered payment flows.",
                },
            ],
        },
    ]

    rules = []
    for r in raw_rules:
        exp = explain(r)
        rule_obj = Rule(
            id=r["id"],
            action=r["action"],
            when=r["when"],
            rationale=r["rationale"],
            evidence=r.get("evidence", {}),
            source="hand",
            added_in="v1",
            title=exp["title"],
            customer_message=exp["customer_message"],
            analyst_note=exp["analyst_note"],
            treatment=exp["treatment"],
            reg_refs=r.get("reg_refs", []),
        )
        rules.append(rule_obj)

    return rules

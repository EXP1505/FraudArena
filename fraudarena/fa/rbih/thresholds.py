"""Owner: M3 (Person A). Threshold resolver (docs/PLAN_IMPLEMENTATION.pdf section 4 and M3-E).

Picks data-backed thresholds from friction_tables.json in data/rbih/current/
(or artifacts/rbih/), matching each feature's friction budget. Writes
fa/rules/derived_thresholds.json with full evidence and falls back to
simulation values from params.yaml if the bundle is absent.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fa.config import load_config

CURRENT_BUNDLE = Path("data/rbih/current")
FALLBACK_BUNDLE = Path("artifacts/rbih")
DERIVED_THRESHOLDS_PATH = Path("fa/rules/derived_thresholds.json")


def _get_friction_tables(bundle_dir: Path | None = None) -> dict[str, Any] | None:
    for candidate in [bundle_dir, CURRENT_BUNDLE, FALLBACK_BUNDLE]:
        if candidate and candidate.exists():
            ft_path = candidate / "friction_tables.json"
            if ft_path.exists():
                try:
                    return json.loads(ft_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
    return None


def resolve_threshold(
    feature: str,
    max_friction_pct: float = 1.0,
    bundle_dir: Path | None = None,
) -> dict[str, Any]:
    """Pick the loosest threshold rung for `feature` where legit_flagged_pct_trainval <= max_friction_pct.
    Returns: {"threshold": float, "op": str, "source": "data"|"simulation", "evidence": {...}}
    """
    data = _get_friction_tables(bundle_dir)
    if data and "tables" in data and feature in data["tables"]:
        rungs = data["tables"][feature]
        # Filter rungs that satisfy the friction budget on train+val
        eligible = [r for r in rungs if r.get("legit_flagged_pct_trainval", 100.0) <= max_friction_pct]
        if eligible:
            # Pick the one that catches the most mules (or the loosest allowed)
            best = max(eligible, key=lambda r: (r.get("mule_flagged_pct_trainval") or 0.0, -r.get("legit_flagged_pct_trainval", 0.0)))
            return {
                "threshold": float(best["threshold"]),
                "op": best["op"],
                "source": "data",
                "evidence": {
                    "feature": feature,
                    "target_max_friction_pct": max_friction_pct,
                    "legit_flagged_pct_trainval": best.get("legit_flagged_pct_trainval"),
                    "mule_flagged_pct_trainval": best.get("mule_flagged_pct_trainval"),
                    "legit_flagged_pct_test": best.get("legit_flagged_pct_test"),
                    "mule_flagged_pct_test": best.get("mule_flagged_pct_test"),
                    "dataset": "RBIH NFPC Phase-2",
                },
            }

    # Fallback to simulation config
    p = load_config().section("rules").get("baseline_v1", {})
    fallback_map = {
        "amount_ratio_30d": (float(p.get("R1_amount_ratio_30d", 10.0)), ">="),
        "payee_age_h": (float(p.get("R2_new_payee_age_h", 1.0)), "<"),
        "n_pay_1h": (float(p.get("R3_n_pay_1h", 8.0)), ">="),
        "sum_1h": (float(p.get("R4_sum_1h", 500000.0)), ">="),
        "fan_out_1h": (float(p.get("R5_fan_out_1h", 8.0)), ">="),
        "r_fan_in_24h": (16.0, ">="),
        "r_passthrough_1h": (0.8, ">="),
    }

    val, op = fallback_map.get(feature, (1.0, ">="))
    return {
        "threshold": val,
        "op": op,
        "source": "simulation",
        "evidence": {"note": "fallback from params.yaml simulation config"},
    }


def generate_derived_thresholds(
    out_path: Path = DERIVED_THRESHOLDS_PATH,
    bundle_dir: Path | None = None,
) -> dict[str, Any]:
    """Resolve thresholds for all policy pack features and write fa/rules/derived_thresholds.json."""
    features_to_resolve = [
        ("amount_ratio_30d", 1.0),
        ("payee_age_h", 0.5),
        ("n_pay_1h", 0.5),
        ("sum_1h", 1.0),
        ("fan_out_1h", 0.5),
        ("r_fan_in_24h", 0.5),
        ("r_passthrough_1h", 1.0),
    ]

    out = {}
    for feat, budget in features_to_resolve:
        out[feat] = resolve_threshold(feat, max_friction_pct=budget, bundle_dir=bundle_dir)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    res = generate_derived_thresholds()
    print("Generated derived thresholds:", json.dumps(res, indent=2))

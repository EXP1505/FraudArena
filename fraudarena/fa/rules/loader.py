"""Owner: M4. Rule loading: baseline v1 from JSON, versions from the release store.

baseline_v1.json is a plain JSON list of rule objects ({id, action, when:[{f,op,v}]})
so api/main.py (M2) can read it directly. Every rule is validated through
fa.contracts.Rule, which rejects unknown features, bad operators and more than
4 conditions. Thresholds come from params.yaml -> rules.baseline_v1.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from fa.config import load_config
from fa.contracts import Rule, RuleSet

BASELINE_PATH = Path(__file__).resolve().parent / "baseline_v1.json"


def rules_from_dicts(items: Iterable[dict[str, Any]]) -> list[Rule]:
    """Validate raw rule dicts. Raises pydantic.ValidationError on a bad rule
    and ValueError on duplicate rule ids."""
    rules = [Rule.model_validate(d) for d in items]
    ids = [r.id for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate rule ids: {sorted({i for i in ids if ids.count(i) > 1})}")
    return rules


def baseline_rules_from_params(params: dict | None = None) -> list[Rule]:
    """Build R1..R6 from params.yaml rules.baseline_v1 (Phase 1 plan section 6)."""
    p = (params if params is not None else load_config().section("rules")).get("baseline_v1", {})
    cond = lambda f, op, v: {"f": f, "op": op, "v": v}  # noqa: E731
    raw = [
        {"id": "R1", "action": "hold", "when": [cond("amount_ratio_30d", ">=", p["R1_amount_ratio_30d"])]},
        {"id": "R2", "action": "hold", "when": [cond("payee_age_h", "<", p["R2_new_payee_age_h"]),
                                                cond("amount_ratio_30d", ">=", p["R2_amount_ratio"])]},
        {"id": "R3", "action": "block", "when": [cond("n_pay_1h", ">=", p["R3_n_pay_1h"])]},
        {"id": "R4", "action": "hold", "when": [cond("device_changed_24h", "==", 1),
                                                cond("sum_1h", ">=", p["R4_sum_1h"])]},
        {"id": "R5", "action": "block", "when": [cond("fan_out_1h", ">=", p["R5_fan_out_1h"])]},
        {"id": "R6", "action": "hold", "when": [cond("night_flag", "==", 1),
                                                cond("amount_ratio_30d", ">=", p["R6_night_amount_ratio"])]},
    ]
    return rules_from_dicts(raw)


def write_baseline_json(path: Path = BASELINE_PATH, params: dict | None = None) -> Path:
    rules = baseline_rules_from_params(params)
    path.write_text(json.dumps([r.model_dump(mode="json") for r in rules], indent=2) + "\n", encoding="utf-8")
    return path


def baseline_source() -> str:
    """"policy_pack" when a verified REAL RBIH bundle is installed (thresholds from data), else "hand".
    FA_BASELINE=hand|policy_pack overrides it (tests pin "hand")."""
    import os

    forced = os.environ.get("FA_BASELINE", "").strip().lower()
    if forced in ("hand", "policy_pack"):
        return forced
    try:
        from fa.rbih import status

        st = status()
        return "policy_pack" if st.get("mode") == "real" and st.get("verified") else "hand"
    except Exception:
        return "hand"


def load_baseline(path: Path = BASELINE_PATH) -> RuleSet:
    """Rule set v1: the RBIH policy pack when a real bundle is installed, else baseline_v1.json."""
    if path == BASELINE_PATH and baseline_source() == "policy_pack":
        from fa.rules.policy_pack import build

        return RuleSet(version="v1", rules=build())
    with open(path, encoding="utf-8") as f:
        return RuleSet(version="v1", rules=rules_from_dicts(json.load(f)))


def load(version: str, store: Any = None) -> RuleSet:
    """Rule set for a version string like "v1" (never edited in place)."""
    from fa.release.versions import default_store

    return (store or default_store()).get(version)


def active(store: Any = None) -> RuleSet:
    """The currently active rule set."""
    from fa.release.versions import default_store

    s = store or default_store()
    return s.get(s.active_version())


if __name__ == "__main__":
    print(f"wrote {write_baseline_json()}")

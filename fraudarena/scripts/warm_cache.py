"""Owner: M1. Runs every scripted LLM call once with network on, so
data/llm_cache/ is warm enough to demo with Wi-Fi off (24h plan section 18).

Requires LLM_API_KEY to be set; walks every playbook's attacker prompt so
the demo never needs a live network call.
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fa.agents.attacker import propose_base_plan
from fa.config import load_config
from fa.plans.playbooks import PARAM_RANGES


def main() -> None:
    config = load_config()
    if not config.llm_api_key:
        raise SystemExit("LLM_API_KEY is not set; cannot warm the cache against the network.")

    seed = config.section("common").get("seed", 42)
    for playbook in PARAM_RANGES:
        plan = propose_base_plan(playbook, params={}, seed=seed)
        print(f"warmed attacker cache for {playbook}: {plan.plan_id} ({len(plan.steps)} steps)")

    print("cache warm. Run `make demo` with Wi-Fi off to confirm it still works.")


if __name__ == "__main__":
    main()

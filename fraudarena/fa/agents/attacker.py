"""Owner: M1. LLM writes a base attack plan (temp 0, cached); validated by
fa.plans.validator, retried up to params.yaml agents.attacker_retry_max
times (24h plan section 7: "Attacker agent").

The LLM only ever returns values within PARAM_RANGES for the chosen
playbook -- never rule text, never the rule set (black box).
"""
from __future__ import annotations

import json

from fa.agents.llm import complete_json
from fa.config import load_config
from fa.contracts import Plan, Playbook
from fa.plans.playbooks import PARAM_RANGES, build_plan
from fa.plans.validator import validate

_PARAM_SCHEMA_CACHE: dict[Playbook, dict] = {}


def _param_schema(playbook: Playbook) -> dict:
    if playbook not in _PARAM_SCHEMA_CACHE:
        props = {
            name: {"type": "number", "minimum": lo, "maximum": hi}
            for name, (lo, hi) in PARAM_RANGES[playbook].items()
        }
        _PARAM_SCHEMA_CACHE[playbook] = {
            "type": "object",
            "required": list(props),
            "properties": props,
        }
    return _PARAM_SCHEMA_CACHE[playbook]


def _prompt(playbook: Playbook, seed: int) -> str:
    ranges = PARAM_RANGES[playbook]
    return (
        f"You are red-teaming a bank's fraud rules in a sandbox. Choose parameter "
        f"values for attack playbook {playbook} (seed={seed}) that are plausible for "
        f"a fraudster trying to move money undetected. Stay within these ranges: "
        f"{json.dumps(ranges)}. Return only the parameter values, nothing about rules "
        f"or detection logic -- you cannot see the bank's rules."
    )


def propose_base_plan(playbook: Playbook, params: dict, seed: int) -> Plan:
    config = load_config()
    max_retries = config.section("agents").get("attacker_retry_max", 2)

    last_violations: list[str] = []
    for attempt in range(max_retries + 1):
        raw_params = complete_json(_prompt(playbook, seed), _param_schema(playbook), key="attacker")
        merged = {**params, **raw_params}
        plan = build_plan(playbook, merged, seed=seed + attempt)
        violations = validate(plan)
        if not violations:
            return plan
        last_violations = violations

    raise ValueError(
        f"attacker could not produce a valid {playbook} plan after "
        f"{max_retries + 1} attempts: {last_violations}"
    )

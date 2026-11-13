"""Owner: M1. defend(trace, rs) -> Rule | None (24h plan section 10).

Selection is code, not the LLM: pick the fa.ml.mine_rules.candidates()
entry with the largest stopped loss subject to added validation FPR <=
params.yaml agents.defender_max_added_fpr_pp. Thresholds are copied
verbatim from the candidate's conditions. The LLM is asked only for
{id, rationale, expected_effect} -- it cannot change conditions; this
module assembles the final Rule object, so the fuzz test (never emits an
unknown feature/operator) holds by construction via fa.contracts.Cond's
own validator.

Retries up to agents.defender_retry_max times against
fa.verify.gates.run_gates() failures; returns None (NO_SAFE_PATCH) if
nothing clears the gates. Coded against M3's mine_rules.candidates and
M4's verify.gates.run_gates, both still stubs owned by other roles.
"""
from __future__ import annotations

from fa.agents.llm import complete_json
from fa.config import load_config
from fa.contracts import Cond, Rule, RuleSet, Trace

_RULE_TEXT_SCHEMA = {
    "type": "object",
    "required": ["id", "rationale", "expected_effect"],
    "properties": {
        "id": {"type": "string"},
        "rationale": {"type": "string"},
        "expected_effect": {"type": "string"},
    },
}


def _select_candidate(candidates: list[dict], max_added_fpr_pp: float) -> dict | None:
    """Pick the candidate with the largest stopped loss, added FPR within budget."""
    eligible = [
        c for c in candidates if c.get("added_fpr_pp", float("inf")) <= max_added_fpr_pp
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda c: c.get("stopped_loss", 0))


def _assemble_rule(candidate: dict, text: dict, version: str) -> Rule:
    conditions = [Cond(**c) for c in candidate["conds"]]
    return Rule(
        id=text["id"],
        action=candidate.get("action", "hold"),
        when=conditions,
        rationale=text["rationale"],
        evidence=candidate.get("evidence", {}),
        source="defender",
        added_in=version,
    )


def defend(trace: Trace, rs: RuleSet) -> Rule | None:
    from fa.ml.mine_rules import candidates as mine_candidates  # M3 stub
    from fa.verify.gates import run_gates  # M4 stub

    config = load_config()
    agents_cfg = config.section("agents")
    max_added_fpr_pp = agents_cfg.get("defender_max_added_fpr_pp", 0.5)
    max_retries = agents_cfg.get("defender_retry_max", 3)

    pool = list(mine_candidates(trace, rs))

    for attempt in range(max_retries):
        candidate = _select_candidate(pool, max_added_fpr_pp)
        if candidate is None:
            return None

        prompt = (
            f"A fraud rule patch is needed. Conditions (fixed, data-derived): "
            f"{candidate['conds']}. Evidence: {candidate.get('evidence', {})}. "
            f"Write only an id, a one-paragraph rationale and the expected effect. "
            f"Do not propose different conditions or thresholds."
        )
        text = complete_json(prompt, _RULE_TEXT_SCHEMA, key="defender")
        rule = _assemble_rule(candidate, text, version=rs.version)

        candidate_rule_set = RuleSet(version=rs.version, rules=[*rs.rules, rule])
        results = run_gates(candidate_rule_set, {"trace": trace, "base_rule_set": rs})
        if all(r.passed for r in results):
            return rule

        pool = [c for c in pool if c is not candidate]

    return None

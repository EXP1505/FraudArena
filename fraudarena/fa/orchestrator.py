"""Owner: M1. Round state machine (24h plan section 2.1):
SELECT -> PLAN -> SEARCH -> EVALUATE -> DEFEND -> VERIFY -> AWAIT_APPROVAL.

Coded against stubs still owned by other roles: M2's api/db.py (round
persistence), M4's rules.loader.active / release.versions (active rule
set, patch proposal), M4's verify.shadow (shadow run before approval).
Writes rounds/plans to DB via M2's helpers; adds lossy plans to
fa.verify.regression.
"""
from __future__ import annotations

import uuid

from fa.agents.attacker import propose_base_plan
from fa.agents.defender import defend
from fa.agents.search import worst_case
from fa.config import load_config

ROUND_STATES = (
    "SELECT",
    "PLAN",
    "SEARCH",
    "EVALUATE",
    "DEFEND",
    "VERIFY",
    "AWAIT_APPROVAL",
    "DONE",
    "NO_SAFE_PATCH",
)


def run_round(playbook: str, started_by: str) -> str:
    """Advance a round through the state machine; return the round_id."""
    from fa.release.versions import propose  # M4 stub
    from fa.rules.loader import active  # M4 stub
    from fa.verify.regression import add as add_regression  # M4 stub

    round_id = f"rnd-{uuid.uuid4().hex[:8]}"
    config = load_config()
    search_cfg = config.section("search")
    seed = config.section("common").get("seed", 42)

    # 1. SELECT
    rs = active()

    # 2. PLAN
    base_plan = propose_base_plan(playbook, params={}, seed=seed)

    # 3. SEARCH
    trace = worst_case(playbook, rs, trials=search_cfg.get("trials", 100), seed=seed)

    # 4. EVALUATE
    if trace.loss_through > 0:
        add_regression(base_plan)

    # 5. DEFEND
    if trace.loss_through == 0:
        return round_id  # nothing to patch; round ends DONE

    rule = defend(trace, rs)
    if rule is None:
        return round_id  # NO_SAFE_PATCH is a valid outcome

    # 6/7. VERIFY + propose for release (gates run inside defend(); here we
    # hand the accepted rule to the release state machine for approval)
    propose(rule, maker="defender-agent")

    return round_id

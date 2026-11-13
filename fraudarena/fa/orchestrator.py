"""Owner: M1. Round state machine (24h plan section 2.1):
SELECT -> PLAN -> SEARCH -> EVALUATE -> DEFEND -> VERIFY -> AWAIT_APPROVAL.

The attacker's base plan (PLAN) is schema/cap-validated but, per
fa.agents.search's frozen signature (worst_case(playbook, rs, trials, seed)
-> Trace, no plan argument), the worst-case SEARCH explores
fa.plans.playbooks.PARAM_RANGES independently rather than literally
continuing from the attacker's steps. The regression set is seeded with
the plan the search actually found (via fa.agents.search.get_plan), not
the unexecuted base plan.

Round persistence (a `rounds` row, so GET /api/rounds/{id} can poll
progress) is M2's job and not wired up yet; this function runs entirely
in-process and returns only the round_id, per docs/TIMELINE.md section 3.
"""
from __future__ import annotations

import uuid

from fa.agents.attacker import propose_base_plan
from fa.agents.defender import defend
from fa.agents.search import get_plan, worst_case
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
    from fa.release.versions import propose
    from fa.rules.loader import active
    from fa.verify.regression import add as add_regression

    round_id = f"rnd-{uuid.uuid4().hex[:8]}"
    config = load_config()
    search_cfg = config.section("search")
    seed = config.section("common").get("seed", 42)

    # 1. SELECT
    rs = active()

    # 2. PLAN (schema/cap-validated attacker proposal; see module docstring
    # for why it is not literally what SEARCH explores)
    propose_base_plan(playbook, params={}, seed=seed)

    # 3. SEARCH
    trace = worst_case(playbook, rs, trials=search_cfg.get("trials", 100), seed=seed)

    # 4. EVALUATE
    if trace.loss_through == 0:
        return round_id  # nothing got through; round ends DONE

    worst_plan = get_plan(trace.plan_id)
    if worst_plan is not None:
        add_regression(worst_plan)

    # 5. DEFEND (runs its own gate pre-check and retries internally)
    rule = defend(trace, rs)
    if rule is None:
        return round_id  # NO_SAFE_PATCH is a valid outcome

    # 6/7. VERIFY + propose for release: ctx triggers the authoritative
    # verify_patch() under the real next version; starter enables the
    # maker-checker check (the round starter cannot also approve it).
    propose(
        rule,
        maker="defender-agent",
        starter=started_by,
        ctx={"trace": trace, "plan": worst_plan},
    )

    return round_id

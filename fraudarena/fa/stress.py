"""Owner: M2/M3. Held-out stress test: how often does a fresh, stronger attacker still get money out?

The patch gates (G2, G4) test a rule on the attack it was written for and on copies of it, so they are
expected to pass. This test is different: the attacker searches again with seeds that were never used by
the search, the variant generator or the gates, a bigger trial budget, and every playbook. We report the
share of (playbook, seed) cases stopped with a 95% Wilson interval, and the worst loss found.
Deterministic: same rule set + same params -> same result.
"""
from __future__ import annotations

from fa.agents.search import random_search_baseline, worst_case
from fa.config import load_config
from fa.contracts import RuleSet
from fa.verify.wilson import wilson_interval

PLAYBOOKS = ("P1", "P2", "P3")


def stress_test(rs: RuleSet, params: dict | None = None) -> dict:
    cfg = params or load_config().section("stress")
    seeds = [int(s) for s in cfg.get("seeds", [7001, 7002, 7003, 7004, 7005])]
    trials = int(cfg.get("trials", 300))
    cases, per = [], {}
    for pb in PLAYBOOKS:
        for seed in seeds:
            # the attacker is allowed whichever searcher does better
            loss = max(int(worst_case(pb, rs, trials, seed).loss_through),
                       int(random_search_baseline(pb, rs, trials, seed + 500).loss_through))
            cases.append({"playbook": pb, "seed": seed, "loss": loss, "stopped": loss == 0})
        mine = [c for c in cases if c["playbook"] == pb]
        per[pb] = {"n": len(mine), "stopped": sum(c["stopped"] for c in mine), "worst_loss": max(c["loss"] for c in mine)}
    n, k = len(cases), sum(c["stopped"] for c in cases)
    lo, hi = wilson_interval(k, n)
    return {"n": n, "stopped": k, "rate": k / n if n else 0.0, "wilson_lo": lo, "wilson_hi": hi,
            "worst_loss": max((c["loss"] for c in cases), default=0), "trials": trials, "seeds": seeds,
            "per_playbook": per, "cases": cases, "version": rs.version}

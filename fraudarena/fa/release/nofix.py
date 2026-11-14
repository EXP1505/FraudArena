"""Owner: M4. When a round ends NO_SAFE_PATCH, explain it: why no rule was proposed, which candidate came closest,
what it would cost, and what a person could do instead. Stored per round so the dashboard can show it.

Nothing here changes any rule. The "ideas" are for a human to consider; the system applies none of them.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from fa.contracts import Cond, Rule, RuleSet
from fa.release.story import plain_rule, rupees

_LOCK = threading.Lock()
MAX_TRIED = 5

GATE_PLAIN = {
    "G2": "It does not actually stop the attack.",
    "G3": "It would let an attack we already fixed succeed again.",
    "G4": "It only stops the exact attack; slightly changed versions still get through.",
    "G5": "It would hold too many honest customers' payments.",
    "G6": "It would hold ordinary payments we always want to allow (like a salary or rent payment).",
}

# What a person could do instead of (or alongside) a blunt rule, by the signal the closest rule relies on.
IDEAS = {
    "payee_age_h": "Instead of holding every payment to a new payee, add a short cool-off or an extra check (a one-time code or call-back) only for the first large payment to a new payee.",
    "sum_1h": "Add a per-hour spending limit for accounts that recently changed device or added a payee, instead of a rule on everyone.",
    "sum_24h": "Add a daily limit that is lower for new payees and for newly seen devices.",
    "sum_newpayee_1h": "Cap how much can go to payees under a day old in one hour.",
    "n_pay_1h": "Add step-up authentication after several payments in an hour, rather than holding them.",
    "n_pay_24h": "Add step-up authentication after many payments in a day, rather than holding them.",
    "fan_out_1h": "Ask for confirmation when a customer pays many different people in an hour.",
    "amount_ratio_30d": "Ask for a one-time code on payments far above the customer's usual size.",
    "device_changed_24h": "Require extra verification for the first payments from a newly seen device.",
    "night_flag": "Use night-time step-up authentication instead of holds.",
    "r_fan_in_24h": "Watch receiving accounts that collect money from many senders and review them by hand.",
    "r_passthrough_1h": "Flag receiving accounts that forward most of what they receive within the hour.",
}


def _path() -> Path:
    return Path(os.environ.get("FA_NOFIX_PATH", "data/nofix_reports.json"))


def _all() -> dict:
    with _LOCK:
        try:
            return json.loads(_path().read_text())
        except (OSError, ValueError):
            return {}


def get(round_id: str) -> dict | None:
    return _all().get(round_id)


def save(round_id: str, report: dict) -> None:
    with _LOCK:
        p = _path()
        try:
            rows = json.loads(p.read_text())
        except (OSError, ValueError):
            rows = {}
        rows[round_id] = report
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, indent=2))
        os.replace(tmp, p)


def clear() -> None:
    with _LOCK:
        try:
            _path().write_text("{}")
        except OSError:
            pass


def _gate_line(g) -> dict:
    ev = g.evidence or {}
    extra = ""
    if g.gate == "G5" and "cand_rate" in ev and "base_rate" in ev:
        extra = (f" It would hold {ev['cand_rate']:.1%} of normal payments, against {ev['base_rate']:.1%} today "
                 f"(the allowed rise is {ev.get('delta', 0.005) * 100:.1f} percentage points).")
    elif g.gate == "G6" and ev.get("n_failures"):
        extra = f" {ev['n_failures']} of our ordinary test payments would be held."
    elif g.gate == "G3" and ev.get("regressed"):
        extra = f" {len(ev['regressed'])} earlier attack(s) would succeed again."
    return {"gate": g.gate, "text": GATE_PLAIN.get(g.gate, g.reason) + extra}


def diagnose(trace, rs: RuleSet, plan=None) -> dict:
    """Build the report for a round that ended with no safe fix."""
    from fa.agents.defender import _build_ctx
    from fa.ml.mine_rules import candidates
    from fa.plans.invent import approach_for
    from fa.verify.gates import run_gates

    report: dict = {"loss_through": trace.loss_through, "loss_text": rupees(trace.loss_through),
                    "approach": approach_for(plan) if plan is not None else None,
                    "tried": 0, "best": None, "ideas": [], "why": ""}
    try:
        pool = candidates(trace, rs)
    except Exception as exc:  # noqa: BLE001
        pool = []
        report["error"] = f"could not mine candidates: {exc}"
    if not pool:
        report["why"] = ("No simple rule could be built that catches this attack. Its payments look like ordinary ones on every signal we "
                         "measure, so any rule that stopped it would not be tied to anything specific about the attack.")
        report["ideas"] = ["Add a signal the rules can see (for example how the customer reached the payment screen), or review this pattern by hand."]
        return report

    ctx = _build_ctx(trace, rs)
    scored = []
    for i, c in enumerate(pool[:MAX_TRIED]):
        rule = Rule(id=f"CAND{i + 1}", action=c.get("action", "hold"), when=[Cond(**x) for x in c["conds"]])
        res = run_gates(RuleSet(version=rs.version, rules=[*rs.rules, rule]), ctx)
        failed = [g for g in res if not g.passed]
        scored.append((len(failed), float(c.get("added_fpr_pp", 99)), c, rule, failed))
    report["tried"] = len(scored)
    scored.sort(key=lambda t: (t[0], t[1]))
    _n, _f, cand, rule, failed = scored[0]
    report["best"] = {
        "rule": plain_rule(rule), "stops": rupees(cand.get("stopped_loss", 0)),
        "problems": [_gate_line(g) for g in failed],
    }
    feats = [c.f for c in rule.when]
    report["ideas"] = [IDEAS[f] for f in dict.fromkeys(feats) if f in IDEAS][:3] or [
        "Review this pattern by hand, or accept the risk for now and keep monitoring."]
    problems = " Also: ".join(p["text"].rstrip(".") + "." for p in report["best"]["problems"][:2])
    if not failed:
        report["why"] = ("The closest candidate rule passed every safety check when re-tested, so this looks like a one-off problem "
                         "while proposing it. Run the round again.")
        return report
    report["why"] = (f"We tried {report['tried']} candidate rules. Each one either failed a safety check or would hurt honest customers, "
                     f"so we proposed nothing instead of a bad rule. The closest one failed because: {problems}")
    return report

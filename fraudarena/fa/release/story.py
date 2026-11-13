"""Owner: M4. The "attack story" stored on every patch, so the second person can see what they approve.

An approver needs four things, in plain words, before clicking Approve:
  1. what the attacker did, step by step, and what the CURRENT rules decided at each step;
  2. why the current rules missed it (each rule, each condition, the actual value);
  3. what the PROPOSED rule is and where it first acts;
  4. what it was tested on (the attack, altered variants, earlier attacks, honest traffic, edge cases).

Everything here is computed by code from a replay; no LLM writes any of it. The result is plain JSON
(`patch["story"]`) so the dashboard only has to display it.
"""
from __future__ import annotations

from typing import Any

from fa.contracts import Cond, Rule, RuleSet

PLAYBOOKS = {"P1": "account takeover, then drain", "P2": "mule chain", "P3": "structuring (many small payments)"}
_OPS = {">=": "at least", ">": "more than", "<=": "at most", "<": "less than", "==": "exactly"}
MONEY_ACTS = ("pay", "cashout")


def rupees(paise: float) -> str:
    return f"₹{paise / 100:,.2f}"


def _num(v: float) -> str:
    return f"{v:g}" if abs(v) < 1e6 else f"{v:,.0f}"


def _hours(h: float) -> str:
    if h < 1:
        return f"{round(h * 60):g} minutes"
    h = round(h, 1)
    return f"{h:g} hours" if h != 1 else "1 hour"


def fmt_value(f: str, v: float) -> str:
    """A feature's actual value, in the unit a person would use."""
    if f == "amount_ratio_30d":
        return f"{v:.2f}× usual"
    if f == "payee_age_h":
        return "brand new" if v == 0 else _hours(v) + " old"
    if f in ("sum_1h", "sum_24h", "sum_newpayee_1h"):
        return rupees(v)
    if f == "r_passthrough_1h":
        return f"{v:.0%}"
    if f in ("device_changed_24h", "night_flag"):
        return "yes" if v else "no"
    return _num(v)


def plain_cond(c: Cond) -> str:
    """One condition as a sentence fragment."""
    op, v, f = _OPS.get(c.op, c.op), c.v, c.f
    if f == "amount_ratio_30d":
        return f"the payment is {op} {_num(v)}× the customer's usual payment"
    if f == "payee_age_h":
        return f"the payee was added {op} {_hours(v)} ago"
    if f == "device_changed_24h":
        return "the customer is on a device first seen in the last 24 hours" if v else "the device is not new"
    if f == "n_pay_1h":
        return f"the customer already made {op} {_num(v)} payments in the last hour"
    if f == "n_pay_24h":
        return f"the customer already made {op} {_num(v)} payments in the last 24 hours"
    if f == "sum_1h":
        return f"the customer already sent {op} {rupees(v)} in the last hour"
    if f == "sum_24h":
        return f"the customer already sent {op} {rupees(v)} in the last 24 hours"
    if f == "sum_newpayee_1h":
        return f"{op} {rupees(v)} went to payees under a day old in the last hour"
    if f == "fan_out_1h":
        return f"the customer paid {op} {_num(v)} different people in the last hour"
    if f == "r_fan_in_24h":
        return f"the receiving account got money from {op} {_num(v)} different senders in the last 24 hours"
    if f == "r_passthrough_1h":
        return f"the receiving account forwarded {op} {v:.0%} of what it received in the last hour"
    if f == "hour_of_day":
        return f"the hour of day is {op} {_num(v)}"
    if f == "night_flag":
        return "it is night (00:00 to 05:00)" if v else "it is daytime"
    return f"{f} {c.op} {_num(v)}"


def plain_rule(rule: Rule) -> str:
    verb = {"hold": "Hold the payment for a check", "block": "Block the payment"}.get(rule.action, rule.action)
    return f"{verb} when " + ", AND ".join(plain_cond(c) for c in rule.when) + "."


def _clock(t: int) -> str:
    h, m = divmod(int(t) // 60, 60)
    return f"+{h}h {m:02d}m" if h else f"+{m}m"


def _step_text(step: Any) -> str:
    who = "Mule account" if step.actor == "mule" else "Victim account"
    if step.act == "login":
        return f"{who} logs in" + (" from a new device" if (step.device or "") == "new" else "")
    if step.act == "add_payee":
        return f"{who} adds a new payee"
    if step.act == "pay":
        return f"{who} pays {rupees(step.amount or 0)}"
    if step.act == "cashout":
        return f"{who} cashes out {rupees(step.amount or 0)}"
    return f"{who}: {step.act}"


def _conds_at(rule: Rule, feats: dict) -> list[dict]:
    out = []
    for c in rule.when:
        actual = feats.get(c.f)
        met = actual is not None and {
            "<": actual < c.v, "<=": actual <= c.v, ">": actual > c.v, ">=": actual >= c.v, "==": actual == c.v,
        }[c.op]
        out.append({"text": plain_cond(c), "actual": None if actual is None else fmt_value(c.f, actual),
                    "met": bool(met)})
    return out


def _gate(gates: list, name: str) -> dict:
    for g in gates or []:
        if g.get("gate") == name:
            return g.get("evidence") or {}
    return {}


def _tested_on(plan: Any, gates: list, loss_before: int, loss_after: int) -> list[dict]:
    g3, g4, g5, g6 = _gate(gates, "G3"), _gate(gates, "G4"), _gate(gates, "G5"), _gate(gates, "G6")
    rows = [{"label": "The attack that got through",
             "detail": f"replayed with the new rule: {rupees(loss_before)} got through before, {rupees(loss_after)} now",
             "ok": loss_after == 0}]
    if g4:
        rows.append({"label": "Altered versions of the attack",
                     "detail": f"{g4.get('stopped')} of {g4.get('n')} variants stopped (needs {g4.get('required', 0.8):.0%})",
                     "ok": g4.get("rate", 0) >= g4.get("required", 0.8)})
    if g3:
        plans = g3.get("plans") or []
        rows.append({"label": "Earlier attacks we already fixed",
                     "detail": f"{len(plans)} checked, none came back" if not g3.get("regressed") else
                               f"{len(g3['regressed'])} came back: {', '.join(g3['regressed'])}",
                     "ok": not g3.get("regressed")})
    if g5:
        rows.append({"label": "Normal customer payments",
                     "detail": f"{g5.get('n', 0):,} payments replayed: held or blocked {g5.get('base_flagged', 0)} before, "
                               f"{g5.get('cand_flagged', 0)} after ({g5.get('new_flags', 0)} newly held)",
                     "ok": not g5.get("new_flags") or g5.get("wilson_hi", 1) <= g5.get("bound", 0.02)})
    if g6:
        rows.append({"label": "Honest but unusual cases (rent to a new landlord, a new phone, festival spending, a new supplier)",
                     "detail": f"{g6.get('cases', 0)} cases, {g6.get('n_failures', 0)} wrongly flagged",
                     "ok": not g6.get("n_failures")})
    return rows



# --------------------------------------------------------------------------- the story, in plain words

# Short names for the starting rules. A rule we have no name for is described by its own sentence.
RULE_TITLES = {
    "R1": "A payment much bigger than the customer's usual",
    "R2": "A big payment to a brand-new payee",
    "R3": "Too many payments in one hour",
    "R4": "New device, then money moving",
    "R5": "Paying many different people quickly",
    "R6": "A large payment at night",
}
HOLD_MEANS = ("'Hold' pauses the payment so the customer (or an analyst) must confirm it before money moves. "
              "'Block' refuses it outright.")


def _dur(seconds: float) -> str:
    if seconds < 90 * 60:
        return f"{max(round(seconds / 60), 1)} minutes"
    h = round(seconds / 3600, 1)
    return f"{h:g} hours"


def rule_title(rule: Rule) -> str:
    return RULE_TITLES.get(rule.id) or ("Rule " + rule.id)


def narrate_plan(plan: Any, trace: Any) -> list[dict]:
    """What the attacker did, as short sentences. Identical repeated payments are grouped, and a long
    pause is called out, because the pause is usually the trick."""
    steps = list(plan.steps)
    feats = [f for (_s, f, _d) in trace.steps]
    biggest_pay = max((st.amount or 0 for st in steps if st.act == "pay"), default=0)
    out: list[dict] = []
    i = 0
    while i < len(steps):
        st = steps[i]
        if i > 0 and st.t - steps[i - 1].t >= 3600:
            out.append({"kind": "wait", "text": f"Waits {_dur(st.t - steps[i - 1].t)}, so the 'new payee' and "
                                                "'new device' warning signs fade."})
        if st.act == "pay" and st.amount:
            j = i
            while j + 1 < len(steps) and steps[j + 1].act == "pay" and steps[j + 1].amount == st.amount \
                    and steps[j + 1].payee == st.payee and steps[j + 1].t - steps[j].t < 3600 * 6:
                j += 1
            n = j - i + 1
            ratio = max(feats[k].get("amount_ratio_30d", 0) for k in range(i, j + 1))
            usual = f" Each is up to {ratio:.2f}× the customer's usual payment." if ratio >= 2 else ""
            if n > 1:
                gap = (steps[j].t - st.t) / (n - 1)
                out.append({"kind": "drain", "text": f"Sends {n} payments of {rupees(st.amount)} to the attacker's account, "
                                                     f"about {_dur(gap)} apart, so no single one looks alarming.{usual}"})
            elif st.amount * 50 < biggest_pay:
                out.append({"kind": "test", "text": f"Sends a tiny test payment of {rupees(st.amount)} to check that money "
                                                    "can leave without setting off an alarm."})
            else:
                out.append({"kind": "drain", "text": f"Pays {rupees(st.amount)} to the attacker's account.{usual}"})
            i = j + 1
            continue
        if st.act == "login":
            new_dev = (st.device or "") == "new"
            out.append({"kind": "setup", "text": "Signs in to the victim's account from a device the bank has never seen "
                                                 "(like a stolen password used on a new phone)." if new_dev
                        else "Signs in to the victim's account."})
        elif st.act == "add_payee":
            out.append({"kind": "setup", "text": "Adds a brand-new payee: an account the attacker controls (a 'mule')."})
        elif st.act == "cashout":
            out.append({"kind": "cashout", "text": f"The mule account withdraws {rupees(st.amount or 0)}. The money is gone."})
        else:
            out.append({"kind": "setup", "text": _step_text(st) + "."})
        i += 1
    return out


def _unmet(rule: Rule, feats: dict) -> list[tuple]:
    """(condition, actual value, relative margin) for every condition that was not met."""
    out = []
    for c in rule.when:
        a = feats.get(c.f)
        ok = a is not None and {"<": a < c.v, "<=": a <= c.v, ">": a > c.v, ">=": a >= c.v, "==": a == c.v}[c.op]
        if not ok:
            margin = 9.99 if a is None else abs(a - c.v) / max(abs(c.v), 1e-9)
            out.append((c, a, margin))
    return out


def breakin_rows(active: RuleSet, feats: dict) -> dict:
    """For each current rule: why it did not fire at the key step, and which one came closest."""
    rows, best = [], None
    for r in active.rules:
        miss = _unmet(r, feats)
        row = {"id": r.id, "title": rule_title(r), "action": r.action, "fired": not miss, "needed": None, "actual": None}
        if miss:
            c, a, margin = miss[0]
            row["needed"], row["actual"] = plain_cond(c), None if a is None else fmt_value(c.f, a)
            score = (len(miss), sum(m for _c, _a, m in miss))
            if best is None or score < best[0]:
                best = (score, row, margin, len(miss))
        rows.append(row)
    near = None
    if best and best[3] == 1 and best[2] < 0.25:
        near = {"id": best[1]["id"], "title": best[1]["title"], "needed": best[1]["needed"], "actual": best[1]["actual"]}
    return {"rows": rows, "closest_call": near}


def resistance_text(story: dict, g4: dict) -> dict:
    lb, la, catch = story["loss_before"], story["loss_after"], story["new_rule"]["catch"]
    if lb == 0:
        text = "The current rules already stop this attack, so the new rule changes nothing for it."
    elif catch and la == 0:
        text = (f"We replayed the exact same attack with the new rule switched on. Everything goes as before until "
                f"step {catch['n']} ({catch['what'].lower()}). The new rule recognises it and holds that step, so the "
                f"attacker's {rupees(lb)} is frozen instead of withdrawn.")
    elif catch:
        text = (f"With the new rule, step {catch['n']} ({catch['what'].lower()}) is held, but {rupees(la)} still gets "
                f"through. The patch only partly works.")
    else:
        text = f"The new rule does not stop any step of this attack: {rupees(la)} still gets through."
    extra = (f"We also tried {g4['n']} re-tuned versions of the attack (different amounts, timing and payees): "
             f"{g4['stopped']} of {g4['n']} were stopped.") if g4 else ""
    return {"text": text, "variants": extra}


def build_story(plan: Any, active: RuleSet, candidate: RuleSet, ctx: dict, gates: list) -> dict:
    """Replay `plan` under both rule sets and describe it for the approver."""
    from fa.plans.executor import execute
    from fa.verify.shadow import fresh_state

    new_rule = candidate.rules[-1]
    before = execute(plan, fresh_state(ctx), active)
    after = execute(plan, fresh_state(ctx), candidate)

    steps, first_stop = [], None
    for i, ((st, feats, d0), (_s, feats1, d1)) in enumerate(zip(before.steps, after.steps)):
        money = st.act in MONEY_ACTS and bool(st.amount)
        newly = money and d0.decision == "allow" and d1.decision != "allow"
        if newly and first_stop is None:
            first_stop = i
        steps.append({"n": i + 1, "when": _clock(st.t), "what": _step_text(st), "money": money,
                      "before": d0.decision, "before_fired": d0.fired,
                      "after": d1.decision, "after_fired": d1.fired, "newly_stopped": newly})

    # The step to explain: the biggest payment the current rules let through (else the cash-out).
    allowed_pays = [(i, st) for i, (st, _f, d) in enumerate(before.steps)
                    if d.decision == "allow" and st.act == "pay" and st.amount]
    key_i = max(allowed_pays, key=lambda x: x[1].amount)[0] if allowed_pays else (
        next((i for i, (st, _f, d) in enumerate(before.steps) if st.act == "cashout"), None))
    key_step = None
    if key_i is not None:
        st, feats, _d = before.steps[key_i]
        key_step = {"n": key_i + 1, "what": _step_text(st),
                    "rules": [{"id": r.id, "action": r.action, "conds": _conds_at(r, feats),
                               "fired": all(c["met"] for c in _conds_at(r, feats))} for r in active.rules]}

    catch = None
    if first_stop is not None:
        st, feats, _d = after.steps[first_stop]
        catch = {"n": first_stop + 1, "what": _step_text(st), "conds": _conds_at(new_rule, feats)}

    pb = PLAYBOOKS.get(getattr(plan, "playbook", ""), getattr(plan, "playbook", "attack"))
    lb, la = before.loss_through, after.loss_through
    if lb == 0:
        headline = f"This attack ({pb}) was already stopped by the rules before this fix; the patch changes nothing for it."
    else:
        headline = (f"An attacker ran a '{pb}' scheme in {len(steps)} steps. Before this fix, the rules ({active.version}) let "
                    f"{rupees(lb)} through. With the proposed rule, {rupees(la)} gets through.")
    key_feats = before.steps[key_i][1] if key_i is not None else {}
    story = {
        "headline": headline, "playbook": getattr(plan, "playbook", None), "playbook_name": pb,
        "plan_id": plan.plan_id, "loss_before": lb, "loss_after": la, "steps": steps,
        "key_step": key_step,
        "new_rule": {"id": new_rule.id, "action": new_rule.action, "plain": plain_rule(new_rule), "catch": catch},
        "tested_on": _tested_on(plan, gates, lb, la),
    }
    story["chapters"] = {
        "attacker": narrate_plan(plan, before),
        "breakin": breakin_rows(active, key_feats) if key_i is not None else {"rows": [], "closest_call": None},
        "fix": {"id": new_rule.id, "plain": plain_rule(new_rule), "means": HOLD_MEANS},
        "resistance": resistance_text(story, _gate(gates, "G4")),
    }
    return story

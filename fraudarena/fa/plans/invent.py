"""Owner: M4. Attack playbooks invented by the attacker LLM.

P1-P3 are fixed, hand-written schemes. This module lets the attacker agent write a NEW scheme of its own:
a short list of steps (login, add payee, pay, cash out) with delays and amounts. The LLM only returns data
in a strict grammar; it never sees the bank's rules and never writes code. Everything it returns goes through
fa.plans.validator (sandbox roles only, <=12 steps, <=72h, money cap), exactly like P1-P3.

The invented scheme is then searched like any playbook: Optuna tunes two knobs (how big the payments are,
how long the waits are) to find the worst case. Because the rest of the pipeline (defender, gates G1-G6,
approval, ledger) only sees a Plan, a new attack needs no other change.

Without an API key the module falls back to a small built-in idea bank so the demo still runs. Those
ideas are labelled `offline-stand-in`, never `llm`.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

from fa.contracts import Plan, Step
from fa.plans.validator import validate

ACTS = ("login", "add_payee", "pay", "cashout")
ACTORS = ("victim", "mule")
VICTIM_MEAN = 100_00                      # paise; same default the built-in playbooks use
MAX_STEPS = 12
MAX_PAY_MULT = 30.0                       # sum of payment sizes, x the victim's usual payment (before scaling)
MAX_DELAY_S = 12 * 3600                   # total waiting in the draft (before scaling)
INVENTED_RANGES = {"amount_scale": (0.3, 2.0), "delay_scale": (0.25, 3.0)}

SPEC_SCHEMA = {
    "type": "object",
    "required": ["name", "approach", "why_it_might_work", "steps"],
    "properties": {
        "name": {"type": "string"},
        "approach": {"type": "string"},
        "why_it_might_work": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["act", "actor", "delay_s"],
                "properties": {
                    "act": {"type": "string", "enum": list(ACTS)},
                    "actor": {"type": "string", "enum": list(ACTORS)},
                    "delay_s": {"type": "number", "minimum": 0, "maximum": MAX_DELAY_S},
                    "amount_mult": {"type": "number", "minimum": 0, "maximum": MAX_PAY_MULT},
                    "payee": {"type": "string"},
                },
            },
        },
    },
}

# Built-in ideas used only when there is no LLM key (and nothing cached). Same grammar the LLM must follow.
IDEA_BANK = [
    {"name": "Slow drip from a fresh device",
     "approach": "Log in from a new device, add one payee, then send many modest payments hours apart so no single payment or burst looks unusual, and cash out at the end.",
     "why_it_might_work": "Each payment is small and the gaps are long, so rules that look at one big payment or a short burst never see anything alarming.",
     "steps": [{"act": "login", "actor": "victim", "delay_s": 0}, {"act": "add_payee", "actor": "victim", "delay_s": 300, "payee": "friend"}]
              + [{"act": "pay", "actor": "victim", "delay_s": 5400, "amount_mult": 3, "payee": "friend"}] * 6
              + [{"act": "cashout", "actor": "mule", "delay_s": 600}]},
    {"name": "Two payees, take turns",
     "approach": "Add two payees and alternate between them, then finish with one larger payment, so no payee ever receives several payments in a row.",
     "why_it_might_work": "Rules that count payments to one payee or watch how many different people are paid in an hour see a calm pattern.",
     "steps": [{"act": "login", "actor": "victim", "delay_s": 0}, {"act": "add_payee", "actor": "victim", "delay_s": 120, "payee": "a"},
               {"act": "add_payee", "actor": "victim", "delay_s": 120, "payee": "b"},
               {"act": "pay", "actor": "victim", "delay_s": 600, "amount_mult": 2, "payee": "a"},
               {"act": "pay", "actor": "victim", "delay_s": 3600, "amount_mult": 2, "payee": "b"},
               {"act": "pay", "actor": "victim", "delay_s": 3600, "amount_mult": 4, "payee": "a"},
               {"act": "pay", "actor": "victim", "delay_s": 7200, "amount_mult": 12, "payee": "b"},
               {"act": "cashout", "actor": "mule", "delay_s": 900}]},
    {"name": "Quick sprint before anyone reacts",
     "approach": "Move money out in a few quick payments within minutes of logging in on a new device, relying on speed rather than stealth.",
     "why_it_might_work": "If a rule needs a history of behaviour to fire, a very short attack finishes before enough history exists.",
     "steps": [{"act": "login", "actor": "victim", "delay_s": 0}, {"act": "add_payee", "actor": "victim", "delay_s": 60, "payee": "quick"},
               {"act": "pay", "actor": "victim", "delay_s": 60, "amount_mult": 8, "payee": "quick"},
               {"act": "pay", "actor": "victim", "delay_s": 90, "amount_mult": 8, "payee": "quick"},
               {"act": "pay", "actor": "victim", "delay_s": 90, "amount_mult": 8, "payee": "quick"},
               {"act": "cashout", "actor": "mule", "delay_s": 120}]},
    {"name": "Mule relay with a long pause",
     "approach": "Send one payment to a first mule, let it sit for hours, then pass it to a second mule that cashes out later.",
     "why_it_might_work": "Long pauses between hops hide the link between the victim's payment and the cash-out.",
     "steps": [{"act": "login", "actor": "victim", "delay_s": 0}, {"act": "add_payee", "actor": "victim", "delay_s": 120, "payee": "mule1"},
               {"act": "pay", "actor": "victim", "delay_s": 300, "amount_mult": 14, "payee": "mule1"},
               {"act": "pay", "actor": "mule", "delay_s": 14400, "amount_mult": 14, "payee": "mule2"},
               {"act": "cashout", "actor": "mule", "delay_s": 7200}]},
]

# ----------------------------------------------------------------------------- registry

_LOCK = threading.Lock()


def _path() -> Path:
    return Path(os.environ.get("FA_INVENTED_PATH", "data/invented_playbooks.json"))


def all_specs() -> list[dict]:
    with _LOCK:
        try:
            return json.loads(_path().read_text())
        except (OSError, ValueError):
            return []


def get_spec(playbook: str) -> dict | None:
    return next((s for s in all_specs() if s["id"] == playbook), None)


def _save(spec: dict) -> None:
    with _LOCK:
        p = _path()
        try:
            rows = json.loads(p.read_text())
        except (OSError, ValueError):
            rows = []
        if any(r["id"] == spec["id"] for r in rows):
            return
        rows.append(spec)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, indent=2))
        os.replace(tmp, p)


def clear() -> None:
    with _LOCK:
        try:
            _path().write_text("[]")
        except OSError:
            pass


# ----------------------------------------------------------------------------- validation + building

def _clean(raw: dict) -> tuple[dict | None, list[str]]:
    """Normalise an LLM answer into a spec, or explain what is wrong with it."""
    bad: list[str] = []
    steps_in = raw.get("steps")
    if not isinstance(steps_in, list) or not steps_in:
        return None, ["`steps` must be a non-empty list"]
    if len(steps_in) > MAX_STEPS:
        bad.append(f"at most {MAX_STEPS} steps (got {len(steps_in)})")
    steps = []
    for i, s in enumerate(steps_in[:MAX_STEPS]):
        if not isinstance(s, dict):
            bad.append(f"step {i + 1} is not an object")
            continue
        act, actor = s.get("act"), s.get("actor")
        if act not in ACTS:
            bad.append(f"step {i + 1}: act must be one of {list(ACTS)}")
        if actor not in ACTORS:
            bad.append(f"step {i + 1}: actor must be victim or mule")
        if act == "cashout" and actor != "mule":
            bad.append(f"step {i + 1}: only a mule cashes out")
        try:
            delay = max(0, int(float(s.get("delay_s", 0))))
            mult = max(0.0, float(s.get("amount_mult", 0) or 0))
        except (TypeError, ValueError):
            bad.append(f"step {i + 1}: delay_s and amount_mult must be numbers")
            continue
        payee = s.get("payee") if isinstance(s.get("payee"), str) and s.get("payee") else None
        if act in ("pay", "add_payee") and not payee:
            payee = "payee1"
        if act == "pay" and mult <= 0:
            bad.append(f"step {i + 1}: a payment needs amount_mult > 0")
        steps.append({"act": act, "actor": actor, "delay_s": delay,
                      **({"amount_mult": mult} if act == "pay" else {}), **({"payee": payee} if payee else {})})
    if not any(s["act"] == "pay" for s in steps):
        bad.append("needs at least one payment")
    if not any(s["act"] == "cashout" for s in steps):
        bad.append("needs a cash-out step (it is the only step that realises a loss)")
    if sum(s.get("amount_mult", 0) for s in steps) > MAX_PAY_MULT:
        bad.append(f"payments add up to more than {MAX_PAY_MULT:g}x the customer's usual payment")
    if sum(s["delay_s"] for s in steps) > MAX_DELAY_S:
        bad.append(f"total waiting exceeds {MAX_DELAY_S // 3600} hours")
    name = str(raw.get("name") or "").strip()[:60]
    if not name:
        bad.append("`name` is required")
    if bad:
        return None, bad
    return {"name": name, "approach": str(raw.get("approach") or "")[:600],
            "why_it_might_work": str(raw.get("why_it_might_work") or "")[:600], "steps": steps}, []


def build_invented(playbook: str, params: dict, seed: int) -> Plan:
    spec = get_spec(playbook)
    if spec is None:
        raise ValueError(f"unknown playbook {playbook!r}")
    return _build(spec, params, seed)


def _build(spec: dict, params: dict, seed: int) -> Plan:
    playbook = spec["id"]
    a, d = float(params.get("amount_scale", 1.0)), float(params.get("delay_scale", 1.0))
    mean = int(params.get("victim_mean_amount", VICTIM_MEAN))
    steps: list[Step] = []
    t, delivered = 0, 0
    for i, s in enumerate(spec["steps"]):
        t += 0 if i == 0 else int(s["delay_s"] * d)
        if s["act"] == "login":
            steps.append(Step(t=t, actor=s["actor"], act="login", device="new"))
        elif s["act"] == "add_payee":
            steps.append(Step(t=t, actor=s["actor"], act="add_payee", payee=s["payee"]))
        elif s["act"] == "pay":
            amt = max(1, int(mean * s["amount_mult"] * a))
            delivered += amt
            steps.append(Step(t=t, actor=s["actor"], act="pay", payee=s["payee"], amount=amt))
        else:
            steps.append(Step(t=t, actor="mule", act="cashout", amount=delivered))
    return Plan(plan_id=f"pl-{playbook}-{seed}", playbook=playbook, seed=seed,
                params={**params, "victim_mean_amount": mean}, steps=steps)


# ----------------------------------------------------------------------------- inventing

def _prompt(existing: list[str], problems: list[str]) -> str:
    return (
        "You are the red-team attacker in a bank's fraud sandbox. Invent ONE new scheme for moving stolen money out "
        "of a customer's account. You cannot see the bank's rules; just think like a fraudster who wants to look normal.\n"
        f"Write it as at most {MAX_STEPS} steps. Each step has: act (login | add_payee | pay | cashout), actor "
        "(victim = the hijacked account, mule = the fraudster's account; only a mule cashes out), delay_s (seconds to wait "
        "after the previous step), and for payments amount_mult (size as a multiple of the customer's usual payment) and "
        f"payee (a short label). Payments must add up to at most {MAX_PAY_MULT:g}x, total waiting at most "
        f"{MAX_DELAY_S // 3600} hours, and the scheme must end with a cashout.\n"
        "Also give: name (3-6 words), approach (2-3 plain sentences: what the attacker does), why_it_might_work (1-2 plain "
        "sentences: what weakness in a typical rule-based fraud system it hopes to exploit).\n"
        f"Already tried, so be clearly different: {json.dumps(existing)}.\n"
        + (f"Your previous answer was rejected: {'; '.join(problems)}. Fix that.\n" if problems else "")
    )


def _finish(clean: dict, source: str, seed: int) -> dict:
    blob = json.dumps(clean["steps"], sort_keys=True) + clean["name"]
    spec = {"id": "X-" + hashlib.sha256(blob.encode()).hexdigest()[:8], **clean, "source": source, "seed": seed}
    problems = validate(_build(spec, {}, 0))             # prove the plan is valid before it is registered
    if problems:
        raise ValueError(f"invented plan failed validation: {problems}")
    _save(spec)
    return get_spec(spec["id"]) or spec


def invent(seed: int = 0) -> dict:
    """Ask the attacker LLM for a new playbook, validate and register it. Returns the stored spec.
    Falls back to the idea bank only when no LLM answer is possible (no key, nothing cached)."""
    from fa.agents.llm import complete_json
    from fa.config import load_config

    existing = [s["name"] for s in all_specs()]
    problems: list[str] = []
    llm_reachable = True
    for attempt in range(3):
        try:
            raw = complete_json(_prompt(existing, problems), SPEC_SCHEMA, key="attacker-invent")
        except RuntimeError as exc:
            if load_config().llm_api_key:               # a real provider error must be seen, not hidden behind stand-ins
                raise ValueError(f"the attacker AI call failed: {exc}") from exc
            llm_reachable = False
            break
        clean, problems = _clean(raw)
        if clean:
            return _finish(clean, "llm", seed)
    if llm_reachable and load_config().llm_api_key:
        raise ValueError(f"the attacker could not invent a valid playbook: {problems}")
    fresh = [i for i in IDEA_BANK if i["name"] not in existing] or IDEA_BANK
    clean, _ = _clean(fresh[(seed + len(existing)) % len(fresh)])
    assert clean, "built-in idea must be valid"
    return _finish(clean, "offline-stand-in", seed)


# ----------------------------------------------------------------------------- the approach, in plain words

BUILTIN = {
    "P1": ("Account takeover, then drain",
           "Take over a customer's account from a new device, add a payee, send a small test payment to see if it is noticed, wait, then move a large amount and cash out.",
           "Rules that only look at single payments miss a test payment followed by a patient drain."),
    "P2": ("Mule chain",
           "Move the money through a chain of mule accounts, in pieces, with pauses between hops, before cashing out.",
           "Each hop looks small and the trail is hard to follow when the money keeps moving."),
    "P3": ("Structuring",
           "Send many payments each just under a limit, spread over several payees and over time.",
           "No single payment crosses a threshold, so threshold rules never fire."),
}


def _dur(s: float) -> str:
    s = float(s)
    return f"{s / 3600:.1f} hours" if s >= 3600 else (f"{s / 60:.0f} minutes" if s >= 60 else f"{s:.0f} seconds")


def _tuned(playbook: str, p: dict) -> list[dict]:
    g = lambda k, d=0: p.get(k, d)
    rs = lambda paise: f"₹{float(paise) / 100:,.2f}"
    if playbook == "P1":
        return [{"label": "First test payment", "value": rs(g("test_amt"))}, {"label": "Wait before the big payment", "value": _dur(g("wait_s"))},
                {"label": "Drain size", "value": f"{g('drain_mult'):.0f}× the customer's usual payment"},
                {"label": "Big payment split into", "value": f"{max(1, int(g('splits', 1)))} part(s), {_dur(g('split_gap_s'))} apart"},
                {"label": "Device first seen", "value": f"{g('device_age_h'):.1f} hours before"}]
    if playbook == "P2":
        return [{"label": "Mule hops", "value": f"{int(g('hops', 1))}"}, {"label": "Pieces per hop", "value": f"{int(g('split_k', 1))}"},
                {"label": "Pause between hops", "value": _dur(g("hop_delay_s"))}, {"label": "Amount", "value": f"{g('amount_mult'):.0f}× the customer's usual payment"}]
    if playbook == "P3":
        return [{"label": "Each payment", "value": f"{g('size_frac') * 100:.0f}% of the ₹50,000 limit"}, {"label": "Payees used", "value": f"{int(g('n_payees', 1))}"},
                {"label": "Payments", "value": f"{int(g('n_payments', 1))}, {_dur(g('spacing_s'))} apart"}]
    return [{"label": "Payment size vs the draft", "value": f"{g('amount_scale', 1):.2f}×"}, {"label": "Waiting time vs the draft", "value": f"{g('delay_scale', 1):.2f}×"}]


def approach_for(plan: Plan) -> dict:
    """What the attacker was trying, in plain words, for the story and the dashboard."""
    pb = plan.playbook
    if pb in BUILTIN:
        name, idea, why = BUILTIN[pb]
        return {"origin": "built-in", "playbook": pb, "name": name, "idea": idea, "why": why, "tuned": _tuned(pb, plan.params)}
    spec = get_spec(pb) or {}
    origin = {"llm": "invented by the attacker AI", "offline-stand-in": "built-in idea (no AI key, so not AI-invented)"}.get(spec.get("source"), "invented")
    return {"origin": origin, "playbook": pb, "name": spec.get("name", pb), "idea": spec.get("approach", ""),
            "why": spec.get("why_it_might_work", ""), "tuned": _tuned(pb, plan.params)}

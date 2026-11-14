"""Owner: M4. Credits: every user starts with 200. Work that costs real compute or AI calls spends credits;
reading, deciding and safety actions are always free.

  Run a round on P1 / P2 / P3 ..... 10   (attacker search + one defender AI call)
  Run a round on a NEW AI attack .. 25   (the AI also invents the attack, then the same search and defence)
  Free: approving, rejecting, rolling back, the story, the change log, the integrity check, exports.
Approving and rolling back must never be paywalled: a person has to be able to act on a risk at 0 credits.
A round that crashes (state ERROR) is refunded. Autopilot spends from whoever started it, round by round.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

START = int(os.environ.get("CREDITS_START", "200"))
COSTS = {"P1": 10, "P2": 10, "P3": 10, "NEW": 25}
KEEP = 60
_LOCK = threading.Lock()


class OutOfCredits(Exception):
    def __init__(self, need: int, have: int):
        super().__init__(f"Not enough credits: this costs {need} and you have {have}.")
        self.need, self.have = need, have


def cost_of(playbook: str) -> int:
    return COSTS.get(playbook, COSTS["NEW"] if playbook.startswith("X-") else COSTS["P1"])


def _path() -> Path:
    return Path(os.environ.get("FA_CREDITS_PATH", "data/credits.json"))


def _load() -> dict:
    try:
        return json.loads(_path().read_text())
    except (OSError, ValueError):
        return {}


def _save(rows: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, indent=2))
    os.replace(tmp, p)


def _acct(rows: dict, user: str) -> dict:
    return rows.setdefault(user, {"balance": START, "spent": 0, "joined": time.time(), "last_seen": None, "history": []})


def _log(a: dict, delta: int, reason: str, ref: str | None) -> None:
    a["history"] = ([{"ts": int(time.time()), "delta": delta, "reason": reason, "ref": ref}] + a["history"])[:KEEP]


def account(user: str) -> dict:
    with _LOCK:
        rows = _load()
        existed = user in rows
        a = _acct(rows, user)
        if not existed:
            _save(rows)
        return json.loads(json.dumps(a))


def charge(user: str, amount: int, reason: str, ref: str | None = None) -> int:
    """Take `amount` credits or raise OutOfCredits. Returns the new balance."""
    with _LOCK:
        rows = _load()
        a = _acct(rows, user)
        if a["balance"] < amount:
            raise OutOfCredits(amount, a["balance"])
        a["balance"] -= amount
        a["spent"] += amount
        _log(a, -amount, reason, ref)
        _save(rows)
        return a["balance"]


def refund(user: str, amount: int, reason: str, ref: str | None = None) -> int:
    """Give credits back once per `ref` (a round crashing twice must not pay twice)."""
    with _LOCK:
        rows = _load()
        a = _acct(rows, user)
        if ref and any(h.get("ref") == ref and h["delta"] > 0 for h in a["history"]):
            return a["balance"]
        a["balance"] += amount
        a["spent"] = max(0, a["spent"] - amount)
        _log(a, amount, reason, ref)
        _save(rows)
        return a["balance"]


def grant(user: str, amount: int, reason: str = "Top-up") -> int:
    with _LOCK:
        rows = _load()
        a = _acct(rows, user)
        a["balance"] += amount
        _log(a, amount, reason, None)
        _save(rows)
        return a["balance"]


def refund_if_failed(user: str, amount: int, round_id: str) -> None:
    """After a round finished: a crashed round (state ERROR…) did not deliver, so it costs nothing."""
    from api.db import get_round
    row = get_round(round_id) or {}
    if str(row.get("state", "")).startswith("ERROR"):
        refund(user, amount, "Refund: the round failed", ref=round_id)


def mark_seen(user: str) -> None:
    with _LOCK:
        rows = _load()
        _acct(rows, user)["last_seen"] = time.time()
        _save(rows)

"""Owner: M4. Autopilot: runs attack rounds one after another with no one pressing "Run round".

It cycles through the chosen playbooks (P1, P2, P3 and/or "NEW" = the attacker LLM invents a scheme),
uses the very same round code as the Run round button, and pauses when too many proposals are waiting for a
person. It never approves anything: every fix still needs a second human (maker-checker is unchanged).
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque

from api import credits
from api.db import get_round, save_round
from fa.release.versions import AWAITING_APPROVAL, default_store

STARTER = "autopilot"
_lock = threading.Lock()
_stop = threading.Event()
_thread: threading.Thread | None = None
_state: dict = {"running": False, "config": None, "done": 0, "total": 0, "current": None,
                "note": "Idle.", "log": deque(maxlen=40), "started_at": None}


def _waiting() -> int:
    return sum(1 for p in default_store().list_patches() if p.get("state") == AWAITING_APPROVAL)


def _say(note: str) -> None:
    _state["note"] = note


def _loop(cfg: dict) -> None:
    from api.routes_rounds import _background_round

    seq = cfg["playbooks"]
    try:
        for i in range(cfg["rounds"]):
            while _waiting() >= cfg["max_pending"] and not _stop.is_set():
                _say(f"Paused: {_waiting()} proposals are waiting for a person to approve or reject them.")
                _stop.wait(2)
            if _stop.is_set():
                break
            pb = seq[i % len(seq)]
            rid = f"rnd-{uuid.uuid4().hex[:8]}"
            cost = credits.cost_of(pb)
            try:
                credits.charge(cfg["user"], cost, f"Autopilot round: {'new AI attack' if pb == 'NEW' else pb}", ref=rid)
            except credits.OutOfCredits as exc:
                _state["log"].appendleft({"ts": int(time.time()), "round_id": None, "playbook": None, "asked_for": pb,
                                          "state": "OUT_OF_CREDITS"})
                _say(f"Stopped: out of credits. {exc}")
                _stop.set()
                break
            _state["current"] = {"round_id": rid, "playbook": pb}
            _say("Inventing a new attack and testing the rules against it…" if pb == "NEW"
                 else f"Attacker is searching for a way past the rules ({pb})…")
            save_round(rid, pb, STARTER, "STARTED")
            _background_round(rid, pb, STARTER)               # same code path as the Run round button
            credits.refund_if_failed(cfg["user"], cost, rid)
            row = get_round(rid) or {}
            _state["log"].appendleft({"ts": int(time.time()), "round_id": rid, "playbook": row.get("playbook", pb),
                                      "asked_for": pb, "state": row.get("state", "?")})
            _state["done"] = i + 1
            _state["current"] = None
            if i + 1 < cfg["rounds"] and cfg["interval_s"] and not _stop.is_set():
                _say(f"Next round in {cfg['interval_s']}s.")
                _stop.wait(cfg["interval_s"])
    except Exception as exc:                                   # never leave the dashboard stuck on "running"
        _state["log"].appendleft({"ts": int(time.time()), "round_id": None, "playbook": None, "asked_for": None,
                                  "state": f"ERROR: {str(exc)[:200]}"})
    finally:
        with _lock:
            _state["running"] = False
            _state["current"] = None
            if not _state["note"].startswith("Stopped: out of credits"):
                _say("Stopped." if _stop.is_set() else f"Finished {_state['done']} rounds. Proposals are waiting on the Story page.")


def start(rounds: int, interval_s: int, playbooks: list[str], max_pending: int, user: str = "demo@local") -> dict:
    global _thread
    with _lock:
        if _state["running"]:
            return status()
        _stop.clear()
        cfg = {"rounds": rounds, "interval_s": interval_s, "playbooks": playbooks, "max_pending": max_pending, "user": user}
        _state.update(running=True, config=cfg, done=0, total=rounds, current=None, started_at=int(time.time()),
                      note="Starting…")
        _thread = threading.Thread(target=_loop, args=(cfg,), daemon=True)
        _thread.start()
    return status()


def stop() -> dict:
    _stop.set()
    return status()


def status() -> dict:
    return {**{k: v for k, v in _state.items() if k != "log"}, "log": list(_state["log"]), "waiting": _waiting()}


def reset() -> None:
    """Forget the log (used by the world reset)."""
    _state["log"].clear()
    _state.update(done=0, total=0, note="Idle.")

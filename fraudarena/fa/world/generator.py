"""Owner: M3. generate_world(seed) -> (State, list[Event]).

    state, events = generate_world(seed)       # frozen interface (TIMELINE section 3)
    world = build_world(seed)                  # dict events + labels, profiles, bounds, sandbox

``state`` is the opening state at ts = 0 (devices and saved payees first seen well
before day 0, empty payment history). ``events`` covers history + validation +
holdout, sorted by ts, ids "e-0000001"...

Splits by time (bounds in sim seconds, end exclusive):
    history     [0, H)          state warm-up, ML train
    validation  [H, H+V)        G5 friction, threshold choice
    holdout     [H+V, H+V+O)    reported numbers only

Sandbox: 40 victims (V-xx) and 20 mules (MU-xx) have normal traffic during history
only, so they have a realistic 30-day profile but never appear in validation or
holdout traffic. Attacks only touch these.

Everything random comes from one numpy.random.default_rng(seed); the same seed gives
the same world_hash.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable, Iterator

import numpy as np

from fa.config import load_config
from fa.contracts import Event, State
from fa.core.clock import DAY
from fa.core.features import compute_features
from fa.core.state import add_account, apply, new_state


# ---------------------------------------------------------------- params

def load_params(params_path: str | None = None) -> dict:
    """Copy of the `world:` section of params.yaml, plus `seed` from `common:`."""
    cfg = load_config(params_path)
    w = json.loads(json.dumps(cfg.section("world")))
    w.setdefault("seed", cfg.section("common").get("seed", 42))
    return w


def bounds(p: dict) -> dict:
    h = int(p["history_days"]) * DAY
    v = h + int(p["validation_days"]) * DAY
    o = v + int(p["holdout_days"]) * DAY
    return {"history": (0, h), "validation": (h, v), "holdout": (v, o)}


def split_of(ts: int, b: dict) -> str:
    for name, (lo, hi) in b.items():
        if lo <= ts < hi:
            return name
    return "outside"


# ---------------------------------------------------------------- accounts

def _profile(rng: np.random.Generator, aid: str, seg: str, p: dict,
             account_pool: list[str], merchants: list[str]) -> dict:
    sp = p["segments"][seg]
    sigma = float(p["amount_sigma"])
    median = sp["median"] * float(rng.lognormal(0.0, p["person_sigma"]))
    rate = sp["rate"] * float(rng.uniform(0.6, 1.4))
    lo, hi = p["devices"]
    n_dev = int(rng.integers(lo, hi + 1))
    devices = {f"D-{aid}-{k}": -int(rng.integers(30, 400)) * DAY for k in range(n_dev)}
    lo, hi = p["saved_payees"]
    n_pay = int(rng.integers(lo, hi + 1))
    payees: list[str] = []
    while len(payees) < n_pay:
        if rng.random() < p["p2p_payee_share"]:
            cand = account_pool[int(rng.integers(len(account_pool)))]
            if cand == aid:
                continue
        else:
            cand = merchants[int(rng.integers(len(merchants)))]
        if cand not in payees:
            payees.append(cand)
    return {
        "segment": seg,
        "median": median,
        "mean": median * math.exp(sigma * sigma / 2),   # mean of the LogNormal
        "rate": rate,
        "devices": devices,
        "payees": {pid: -int(rng.integers(30, 400)) * DAY for pid in payees},
    }


def make_profiles(rng: np.random.Generator, p: dict) -> tuple[dict, dict]:
    """Customers, sandbox victims and mules, merchants. Returns (profiles, ids)."""
    seg_names = list(p["segments"])
    seg_p = np.array([p["segments"][s]["share"] for s in seg_names], dtype=float)
    seg_p /= seg_p.sum()
    ids = {
        "customers": [f"A-{i:04d}" for i in range(int(p["customers"]))],
        "victims": [f"V-{i:02d}" for i in range(int(p.get("sandbox_victims", 0)))],
        "mules": [f"MU-{i:02d}" for i in range(int(p.get("sandbox_mules", 0)))],
        "merchants": [f"M-{i:04d}" for i in range(int(p["merchants"]))],
    }
    profiles: dict[str, dict] = {}
    for aid in ids["customers"] + ids["victims"] + ids["mules"]:
        seg = seg_names[int(rng.choice(len(seg_names), p=seg_p))]
        profiles[aid] = _profile(rng, aid, seg, p, ids["customers"], ids["merchants"])
    return profiles, ids


def build_world(seed: int | None = None, params: dict | None = None) -> dict:
    from fa.world.normal import generate_traffic

    p = params or load_params()
    if seed is not None:
        p = {**p, "seed": int(seed)}
    rng = np.random.default_rng(int(p["seed"]))
    b = bounds(p)

    profiles, ids = make_profiles(rng, p)
    victims, mules, merchants = ids["victims"], ids["mules"], ids["merchants"]
    state = new_state()
    for aid, prof in profiles.items():
        add_account(state, aid, balance=int(prof["mean"] * 60),
                    payees=prof["payees"], devices=prof["devices"])

    active = {aid: b["history"][1] // DAY for aid in victims + mules}   # history only
    events, labels = generate_traffic(rng, profiles, p, b["holdout"][1] // DAY, active)

    return {"state": state, "events": events, "labels": labels, "profiles": profiles,
            "bounds": b, "sandbox": {"victims": victims, "mules": mules},
            "merchants": merchants, "params": p}


def generate_world(seed: int | None = None) -> tuple[State, list[Event]]:
    """Frozen interface: (opening state, contract Events for history + validation +
    holdout). Use build_world() if you also need labels, bounds or sandbox ids."""
    w = build_world(seed)
    return w["state"], [Event(**e) for e in w["events"]]


# ---------------------------------------------------------------- replay helpers

def replay(state: State, events: Iterable[Any], decide_fn=None) -> Iterator[tuple]:
    """Features then apply, in order (mutates ``state``).

    Yields (event, features, decision). ``decide_fn(features, event) -> str`` defaults
    to allow-all.
    """
    for ev in events:
        feats = compute_features(state, ev)          # BEFORE apply (leakage rule)
        d = decide_fn(feats, ev) if decide_fn else "allow"
        apply(state, ev, d)
        yield ev, feats, d


def sandbox_state(params: dict | None = None):
    """Start state for attack plans: accounts "victim" and "mule" (the roles plans use), the
    victim with an old device, a saved payee and ordinary daily payments, so features such
    as amount_ratio_30d are meaningful. Plan steps start at t = 0."""
    ep = params or load_config().section("ml")["export"]
    state = new_state()
    add_account(state, "victim", balance=10**9, payees={"saved": -60 * DAY}, devices={"D-old": -90 * DAY})
    add_account(state, "mule", balance=0)
    for k in range(int(ep["victim_history_payments"])):
        apply(state, {"event_id": f"vh-{k}", "ts": -(k + 1) * DAY + 14 * 3600, "type": "payment",
                      "account": "victim", "device": "D-old", "payee": "saved",
                      "amount": int(ep["victim_payment_paise"]), "channel": "upi"}, "allow")
    return state


def warm_state(world: dict, until: int | None = None) -> State:
    """Opening state with all events before ``until`` (default: end of history)
    applied as allowed. This is the state to snapshot for the attacker search."""
    from fa.core.snapshot import restore
    until = world["bounds"]["history"][1] if until is None else until
    state = restore(world["state"])
    for _ in replay(state, (e for e in world["events"] if e["ts"] < until)):
        pass
    return state


def events_in(world: dict, split: str) -> list[dict]:
    lo, hi = world["bounds"][split]
    return [e for e in world["events"] if lo <= e["ts"] < hi]


def world_hash(events: Iterable[dict]) -> str:
    """SHA-256 over the canonical JSON of the event stream (determinism check)."""
    h = hashlib.sha256()
    for ev in events:
        h.update(json.dumps(ev, sort_keys=True, separators=(",", ":")).encode())
    return h.hexdigest()


if __name__ == "__main__":
    import time
    from collections import Counter
    t0 = time.perf_counter()
    w = build_world()
    dt = time.perf_counter() - t0
    c = Counter(e["type"] for e in w["events"])
    per = {k: len(events_in(w, k)) for k in w["bounds"]}
    print(f"seed={w['params']['seed']} accounts={len(w['profiles'])} events={len(w['events'])} "
          f"{dict(c)} in {dt:.1f}s")
    print(f"per split: {per}")
    print(f"look-alikes: {dict(Counter(w['labels'].values()))}")
    print(f"world_hash={world_hash(w['events'])}")

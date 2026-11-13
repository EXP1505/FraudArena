# Owner: M3. World determinism, splits, sandbox, look-alikes, normal-traffic friction.
import pytest

from fa.contracts import Event, State
from fa.core import snapshot
from fa.core.clock import DAY
from fa.world.generator import build_world, events_in, generate_world, warm_state, world_hash
from fa.world.generator import load_params

SMALL = {**load_params(), "customers": 150, "sandbox_victims": 6, "sandbox_mules": 4,
         "history_days": 10, "validation_days": 3, "holdout_days": 3, "merchants": 50}


@pytest.fixture(scope="module")
def world():
    return build_world(seed=7, params=dict(SMALL))


def test_same_seed_identical_world():
    a = build_world(seed=123, params=dict(SMALL))
    b = build_world(seed=123, params=dict(SMALL))
    assert world_hash(a["events"]) == world_hash(b["events"]) and a["labels"] == b["labels"]
    assert a["state"] == b["state"]
    assert world_hash(build_world(seed=124, params=dict(SMALL))["events"]) != world_hash(a["events"])


def test_generate_world_interface():
    state, events = generate_world(seed=1)        # full size from params.yaml (~4 s)
    assert isinstance(state, State) and len(events) > 50_000 and isinstance(events[0], Event)
    assert events == sorted(events, key=lambda e: e.ts)


def test_events_sorted_typed_and_in_horizon(world):
    ts = [e["ts"] for e in world["events"]]
    assert ts == sorted(ts) and ts[0] >= 0 and ts[-1] < world["bounds"]["holdout"][1]
    assert {e["type"] for e in world["events"]} <= {"login", "add_payee", "payment", "cashout"}
    assert len({e["event_id"] for e in world["events"]}) == len(world["events"])
    assert all(isinstance(e["amount"], int) for e in world["events"])


def test_sandbox_only_in_history(world):
    sandbox = set(world["sandbox"]["victims"]) | set(world["sandbox"]["mules"])
    hist_end = world["bounds"]["history"][1]
    in_hist = {e["account"] for e in world["events"] if e["ts"] < hist_end}
    later = {e["account"] for e in world["events"] if e["ts"] >= hist_end}
    assert sandbox & in_hist and not (sandbox & later)


def test_lookalikes_present(world):
    tags = set(world["labels"].values())
    assert {"rent_new_landlord", "post_phone_change", "festival"} <= tags
    pays = sum(e["type"] == "payment" for e in world["events"])
    la = sum(1 for e in world["events"] if e["type"] == "payment" and e["event_id"] in world["labels"])
    assert 0.005 < la / pays < 0.05


def test_warm_state_and_snapshot_speed(world):
    import time
    st = warm_state(world)
    snap = snapshot.take(st)
    t = time.perf_counter()
    for _ in range(5):
        snapshot.restore(snap)
    assert (time.perf_counter() - t) / 5 < 0.05


def test_splits_partition(world):
    n = sum(len(events_in(world, k)) for k in ("history", "validation", "holdout"))
    assert n == len(world["events"])


def test_normal_friction_measured(world):
    """Report v1 hold+block on validation normal traffic. Phase 1 target is < 1%;
    G5's hard budget is a 2% Wilson upper bound. The number goes to M4 for tuning."""
    from fa.metrics import normal_friction
    r = normal_friction(world=world, split="validation")
    assert r["payments"] > 500
    assert r["rate"] <= 0.02, r           # sanity only; the real budget is enforced by G5

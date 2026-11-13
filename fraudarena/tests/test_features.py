# Owner: M3. Clock, state/apply, snapshot, and every feature on hand-built events.
import pytest

from fa.core import snapshot
from fa.core.clock import DAY, HOUR, MINUTE, Clock, hour_of_day
from fa.core.features import FEATURES, compute_features
from fa.core.state import add_account, apply, new_state

OLD = -60 * DAY
_n = [0]


def ev(ts, type="payment", account="A", amount=0, payee=None, device="D1"):
    _n[0] += 1
    return {"event_id": f"e-{_n[0]}", "ts": ts, "type": type, "account": account,
            "device": device, "payee": payee, "amount": amount, "channel": "upi"}


def fresh():
    s = new_state()
    add_account(s, "A", balance=10**9, payees={"P1": OLD, "P2": OLD}, devices={"D1": OLD})
    add_account(s, "B", balance=10**8, devices={"DB": OLD})
    return s


def pays(s, t0, amounts, payee="P1", step=60):
    for i, a in enumerate(amounts):
        apply(s, ev(t0 + i * step, amount=a, payee=payee))


# ---- clock
def test_clock():
    c = Clock(100)
    assert c.now() == 100 and c.advance(50) == 150
    with pytest.raises(ValueError):
        c.advance(-1)
    assert hour_of_day(23 * HOUR + 59 * MINUTE) == 23 and hour_of_day(DAY) == 0


# ---- snapshot: take, run events, restore == snapshot
def test_snapshot_restore_roundtrip():
    s = fresh()
    pays(s, 1000, [100] * 20)
    snap = snapshot.take(s)
    ref = snapshot.take(snap)
    for i in range(100):
        apply(s, ev(5000 + i * 30, amount=7, payee=f"X{i % 9}", device=f"D{i % 3}"),
              ["allow", "hold", "block"][i % 3])
    assert s != snap and snap == ref
    back = snapshot.restore(snap)
    assert back == ref
    back.accounts["A"].payees["Z"] = 1
    back.accounts["A"].recent_pays.append((1, 1, "Z"))
    assert snap == ref                       # restore is independent of the snapshot


# ---- leakage: features never see the event itself or anything later
def test_no_leakage_from_future():
    s = fresh()
    events = []
    for i in range(300):
        events.append(ev(DAY + i * 97, amount=100 + (i * 37) % 900, payee=f"P{i % 11}",
                         device="D1" if i % 7 else "D2"))
        if i % 5 == 0:
            events.append(ev(DAY + i * 97 + 3, type="payment", account="B",
                             amount=50, payee="A", device="DB"))
    before = {}
    for e in events:
        before[e["event_id"]] = compute_features(s, e)
        apply(s, e)
    for e in events:                          # state now holds every event, incl. later ones
        assert compute_features(s, e) == before[e["event_id"]], e


def test_current_event_not_counted():
    f = compute_features(fresh(), ev(1000, amount=500, payee="P1"))
    assert f["n_pay_1h"] == 0 and f["sum_1h"] == 0 and f["fan_out_1h"] == 0


# ---- amount_ratio_30d
def test_amount_ratio_30d():
    s = fresh()
    assert compute_features(s, ev(10, amount=3000, payee="P1"))["amount_ratio_30d"] == 1.0
    pays(s, 100, [100, 200])
    assert compute_features(s, ev(500, amount=3000, payee="P1"))["amount_ratio_30d"] == 1.0
    pays(s, 300, [300])                                          # 3 pays, mean 200
    assert compute_features(s, ev(500, amount=1000, payee="P1"))["amount_ratio_30d"] == pytest.approx(5.0)
    # 30 days later they have left the window
    assert compute_features(s, ev(30 * DAY + 400, amount=1000, payee="P1"))["amount_ratio_30d"] == 1.0
    # held payments do not count toward the average
    apply(s, ev(600, amount=10**6, payee="P1"), "hold")
    assert compute_features(s, ev(700, amount=1000, payee="P1"))["amount_ratio_30d"] == pytest.approx(5.0)


# ---- payee_age_h
def test_payee_age_grows():
    s = fresh()
    c = Clock(10 * DAY)
    assert compute_features(s, ev(c.now(), type="add_payee", payee="NEW"))["payee_age_h"] == 0
    apply(s, ev(c.now(), type="add_payee", payee="NEW"))
    assert compute_features(s, ev(c.now(), amount=10, payee="NEW"))["payee_age_h"] == 0
    c.advance(10 * MINUTE)
    assert compute_features(s, ev(c.now(), amount=10, payee="NEW"))["payee_age_h"] == pytest.approx(1 / 6)
    c.advance(110 * MINUTE)
    assert compute_features(s, ev(c.now(), amount=10, payee="NEW"))["payee_age_h"] == pytest.approx(2.0)
    assert compute_features(s, ev(c.now(), amount=10, payee="NEVER"))["payee_age_h"] == 0


# ---- device_changed_24h (about the device in use; first seen < 24 h ago)
def test_device_changed_24h():
    s = fresh()
    t = 3 * DAY
    f = compute_features(s, ev(t, amount=10, payee="P1"))
    assert f["device_changed_24h"] == 0
    f = compute_features(s, ev(t, amount=10, payee="P1", device="D9"))
    assert f["device_changed_24h"] == 1
    apply(s, ev(t, type="login", device="D9"))
    f = compute_features(s, ev(t + 5 * HOUR, amount=1, payee="P1", device="D9"))
    assert f["device_changed_24h"] == 1
    assert compute_features(s, ev(t + 25 * HOUR, amount=1, payee="P1", device="D9"))["device_changed_24h"] == 0
    # an old device in use is not "changed" even if a new one was added recently
    assert compute_features(s, ev(t + 5 * HOUR, amount=1, payee="P1", device="D1"))["device_changed_24h"] == 0


# ---- counts and sums, fan-out window
def test_counts_sums_fan_out_window():
    s = fresh()
    t0 = 5 * DAY
    apply(s, ev(t0, amount=10, payee="OLDP"))
    for k, p in enumerate(["X1", "X2", "X2", "X3", "X1"]):
        apply(s, ev(t0 + 30 * MINUTE + k * MINUTE, amount=10, payee=p))
    f = compute_features(s, ev(t0 + HOUR + 5 * MINUTE, amount=10, payee="X4"))
    assert f["fan_out_1h"] == 3 and f["n_pay_1h"] == 5 and f["n_pay_24h"] == 6
    assert f["sum_1h"] == 50 and f["sum_24h"] == 60
    # boundary: exactly 1 h old is outside the window
    assert compute_features(s, ev(t0 + HOUR, amount=1, payee="Q"))["n_pay_1h"] == 5
    # blocked payments do not count
    apply(s, ev(t0 + HOUR + 6 * MINUTE, amount=10, payee="X9"), "block")
    assert compute_features(s, ev(t0 + HOUR + 7 * MINUTE, amount=1, payee="Q"))["fan_out_1h"] == 3


def test_sum_newpayee_1h():
    s = fresh()
    t = 3 * DAY
    apply(s, ev(t, type="add_payee", payee="N1"))
    apply(s, ev(t + 100, amount=700, payee="N1"))
    apply(s, ev(t + 200, amount=50, payee="P1"))           # old payee
    apply(s, ev(t + 300, amount=40, payee="N2"))           # implicitly new
    assert compute_features(s, ev(t + 400, amount=1, payee="P2"))["sum_newpayee_1h"] == 740


# ---- receiving side
def test_fan_in_and_passthrough():
    s = fresh()
    add_account(s, "C", balance=10**8, devices={"DC": OLD})
    t = 3 * DAY
    apply(s, ev(t, account="A", amount=1000, payee="B"))
    apply(s, ev(t + 60, account="C", amount=1000, payee="B", device="DC"))
    apply(s, ev(t + 120, type="cashout", account="B", amount=1000, device="DB"))
    f = compute_features(s, ev(t + 200, account="A", amount=5, payee="B"))
    assert f["r_fan_in_24h"] == 2 and f["r_passthrough_1h"] == pytest.approx(0.5)
    f = compute_features(s, ev(t + 200, type="cashout", account="B", amount=500, device="DB"))
    assert f["r_passthrough_1h"] == pytest.approx(0.5)            # recipient = the account itself
    assert compute_features(s, ev(t + 200, amount=5, payee="UNKNOWN"))["r_fan_in_24h"] == 0
    f = compute_features(s, ev(t + 2 * HOUR, amount=5, payee="B"))
    assert f["r_passthrough_1h"] == 0 and f["r_fan_in_24h"] == 2  # no inflow in last hour


# ---- time
def test_time_features_and_names():
    s = fresh()
    f = compute_features(s, ev(2 * DAY + 4 * HOUR + 59 * MINUTE, amount=1, payee="P1"))
    assert f["hour_of_day"] == 4 and f["night_flag"] == 1
    f = compute_features(s, ev(2 * DAY + 5 * HOUR, amount=1, payee="P1"))
    assert f["hour_of_day"] == 5 and f["night_flag"] == 0
    assert tuple(f) == FEATURES


# ---- apply semantics
def test_apply_hold_block_allow():
    s = fresh()
    bal = s.accounts["A"].balance
    apply(s, ev(100, amount=999, payee="NEWP", device="DX"), "hold")
    a = s.accounts["A"]
    assert a.balance == bal and a.recent_pays == [] and len(a.pending) == 1
    assert "NEWP" in a.payees and "DX" in a.devices
    apply(s, ev(200, amount=5, payee="P1"), "block")
    assert a.balance == bal and len(a.pending) == 1
    apply(s, ev(300, amount=500, payee="B"))
    assert a.balance == bal - 500 and s.accounts["B"].balance == 10**8 + 500
    with pytest.raises(ValueError):
        apply(s, ev(400, amount=1, payee="P1"), "maybe")


def test_phase1_aliases_accepted():
    s = fresh()
    apply(s, {"id": "x", "ts": 10, "type": "payee_add", "account": "A", "payee": "Q"})
    apply(s, {"id": "y", "ts": 20, "type": "pay", "account": "A", "payee": "Q", "amount": 5})
    assert s.accounts["A"].recent_pays == [(20, 5, "Q")]


# ---- the three CP1 gate events, at the feature level
def test_gate_scenarios_features():
    s = fresh()
    t = 4 * DAY + 12 * HOUR
    pays(s, t - 6 * HOUR, [100_000] * 5)                      # mean 1,000 rupees
    assert compute_features(s, ev(t, amount=80_000, payee="P1"))["amount_ratio_30d"] < 3
    apply(s, ev(t, type="add_payee", payee="NEWLL"))
    f = compute_features(s, ev(t + 10 * MINUTE, amount=500_000, payee="NEWLL"))
    assert f["payee_age_h"] < 1 and 3 <= f["amount_ratio_30d"] < 10   # R2 only, not R1
    for k in range(8):
        apply(s, ev(t + HOUR + k * 60, amount=100, payee=f"F{k}"))
    assert compute_features(s, ev(t + HOUR + 9 * 60, amount=100, payee="F8"))["fan_out_1h"] == 8


# ---- compatibility with M1's contracts
def test_contract_types_roundtrip():
    from fa.contracts import Event, State
    from fa.core.state import new_state
    s = new_state()
    assert isinstance(s, State)
    e = Event(event_id="c1", ts=100, type="payment", account="A", device="D1", payee="P", amount=500)
    f = compute_features(s, e)
    assert tuple(f) == FEATURES and all(isinstance(v, float) for v in f.values())
    apply(s, e, "allow")
    assert s.account("A").recent_pays == [(100, 500, "P")]
    # a plain contract State also works (receiving-side features just stay 0)
    plain = State()
    apply(plain, e, "allow")
    assert compute_features(plain, Event(event_id="c2", ts=200, type="payment", account="A",
                                         payee="P", amount=1))["n_pay_1h"] == 1.0

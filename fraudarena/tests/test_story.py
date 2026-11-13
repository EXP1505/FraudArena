"""Owner: M4. The attack story the approver reads: accurate numbers, plain words, never blocks verification."""
from __future__ import annotations

import pytest

from fa.contracts import Cond, Rule
from fa.release import story as story_mod
from fa.release import versions
from fa.release.versions import VersionStore
from tests.test_release import GOOD, attack, noon_payment


@pytest.fixture
def store(tmp_path):
    return VersionStore(tmp_path / "s")


@pytest.fixture
def ctx():
    return {"plan": attack("pl-fail"), "regression_plans": [attack("pl-old")],
            "variants": [attack(f"pl-v{i}", start=i * 600) for i in range(10)],
            "normal_events": [noon_payment(i) for i in range(2000)],
            "golden_cases": [[noon_payment(i)] for i in range(3)]}


def test_story_is_stored_with_the_real_numbers(store, ctx):
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=store)
    s = store.get_patch(pid)["story"]
    # Under the real v1 rules the ₹48,000 payment is already HELD; only the ₹1.00 test payment (and its
    # cash-out) gets through. The story must report exactly that, not an invented bigger loss.
    assert s["loss_before"] == 100 and s["loss_after"] == 0
    assert "₹1.00 through" in s["headline"] and "₹0.00" in s["headline"] and "5 steps" in s["headline"]
    assert [x["n"] for x in s["steps"]] == [1, 2, 3, 4, 5]
    assert [x["before"] for x in s["steps"]] == ["allow", "allow", "allow", "hold", "allow"]
    stopped = [x["n"] for x in s["steps"] if x["newly_stopped"]]
    assert stopped == [3, 5]                                            # the test payment and the cash-out
    assert s["steps"][3]["what"] == "Victim account pays ₹48,000.00" and not s["steps"][3]["newly_stopped"]


def test_story_explains_why_each_current_rule_missed(store, ctx):
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=store)
    k = store.get_patch(pid)["story"]["key_step"]
    assert k["n"] == 3 and k["what"] == "Victim account pays ₹1.00"     # the biggest payment the rules ALLOWED
    assert [r["id"] for r in k["rules"]] == ["R1", "R2", "R3", "R4", "R5", "R6"]
    assert not any(r["fired"] for r in k["rules"])                      # that is why it got through
    r1 = k["rules"][0]["conds"][0]
    assert r1["text"] == "the payment is at least 10× the customer's usual payment" and r1["actual"]
    assert all(c["actual"] is not None for r in k["rules"] for c in r["conds"])


def test_story_describes_the_new_rule_and_what_it_was_tested_on(store, ctx):
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=store)
    s = store.get_patch(pid)["story"]
    assert s["new_rule"]["plain"] == "Hold the payment for a check when it is night (00:00 to 05:00)."
    assert s["new_rule"]["catch"]["n"] == 3 and s["new_rule"]["catch"]["conds"][0]["met"]
    labels = [t["label"] for t in s["tested_on"]]
    assert len(labels) == 5 and all(t["ok"] for t in s["tested_on"])
    assert "2,000 payments replayed" in next(t["detail"] for t in s["tested_on"] if t["label"] == "Normal customer payments")
    assert "10 of 10 variants stopped" in next(t["detail"] for t in s["tested_on"] if t["label"].startswith("Altered versions"))


def test_story_is_recorded_even_for_a_rejected_patch(store, ctx):
    bad = Rule(id="R-never", action="hold", when=[Cond(f="n_pay_1h", op=">=", v=999)])
    pid = versions.propose(bad, "defender-agent", starter="alice", ctx=ctx, store=store)
    p = store.get_patch(pid)
    assert p["state"] == versions.REJECTED
    assert p["story"]["loss_after"] == 100 and p["story"]["new_rule"]["catch"] is None
    assert not p["story"]["tested_on"][0]["ok"]


def test_a_failing_story_never_blocks_verification(store, ctx, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("renderer broke")

    monkeypatch.setattr(story_mod, "build_story", boom)
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=store)
    p = store.get_patch(pid)
    assert p["state"] == versions.AWAITING_APPROVAL and "renderer broke" in p["story"]["error"]


def test_no_plan_means_no_story(store, ctx):
    del ctx["plan"]
    ctx["golden_cases"], ctx["variants"] = [[noon_payment(0)]], [attack("v")]
    pid = versions.propose(GOOD, "m", starter="alice", ctx=ctx, store=store)
    assert store.get_patch(pid)["story"] is None


@pytest.mark.parametrize("cond,text", [
    (Cond(f="payee_age_h", op="<", v=0.25), "the payee was added less than 15 minutes ago"),
    (Cond(f="payee_age_h", op="<", v=1), "the payee was added less than 1 hour ago"),
    (Cond(f="sum_1h", op=">=", v=50000), "the customer already sent at least ₹500.00 in the last hour"),
    (Cond(f="device_changed_24h", op="==", v=1), "the customer is on a device first seen in the last 24 hours"),
    (Cond(f="r_fan_in_24h", op=">", v=0), "the receiving account got money from more than 0 different senders in the last 24 hours"),
])
def test_plain_conditions_read_like_sentences(cond, text):
    assert story_mod.plain_cond(cond) == text


def test_every_feature_has_plain_words_and_never_leaks_its_raw_name():
    from fa.contracts import FEATURES

    for f in FEATURES:
        text = story_mod.plain_cond(Cond(f=f, op=">=", v=1))
        assert text and f not in text, (f, text)


def test_values_are_shown_in_human_units():
    assert story_mod.fmt_value("payee_age_h", 11.6989) == "11.7 hours old"
    assert story_mod.fmt_value("payee_age_h", 0) == "brand new"
    assert story_mod.fmt_value("amount_ratio_30d", 9.97) == "9.97× usual"
    assert story_mod.fmt_value("sum_1h", 91051) == "₹910.51"
    assert story_mod.fmt_value("night_flag", 1) == "yes"


# ------------------------------------------------------------------ the story in plain words

def _trace(plan):
    from fa.plans.executor import execute
    from fa.rules.loader import load_baseline
    from fa.verify.shadow import fresh_state

    return execute(plan, fresh_state({}), load_baseline())


def test_attacker_narration_reads_like_a_story(store, ctx):
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=store)
    att = store.get_patch(pid)["story"]["chapters"]["attacker"]
    assert [a["kind"] for a in att] == ["setup", "setup", "test", "drain", "cashout"]
    assert "device the bank has never seen" in att[0]["text"] and "mule" in att[1]["text"]
    assert "tiny test payment of ₹1.00" in att[2]["text"]
    assert att[4]["text"] == "The mule account withdraws ₹48,000.00. The money is gone."
    assert all("_" not in a["text"] for a in att)                     # no raw feature names leak into the prose


def test_a_long_pause_and_repeated_payments_are_called_out():
    from fa.contracts import Plan, Step

    steps = [Step(t=0, actor="victim", act="login", device="new"), Step(t=60, actor="victim", act="add_payee", payee="mule")]
    steps += [Step(t=5 * 3600 + i * 2880, actor="victim", act="pay", payee="mule", amount=91_051) for i in range(3)]
    steps += [Step(t=8 * 3600, actor="mule", act="cashout", amount=273_153)]
    plan = Plan(plan_id="pl-x", playbook="P1", seed=1, steps=steps)
    text = " ".join(a["text"] for a in story_mod.narrate_plan(plan, _trace(plan)))
    assert "Waits 5 hours" in text and "Sends 3 payments of ₹910.51" in text and "about 48 minutes apart" in text


def test_breakin_lists_every_current_rule_and_flags_a_near_miss():
    from fa.contracts import Plan, Step
    from fa.rules.loader import load_baseline

    feats = {"amount_ratio_30d": 9.97, "payee_age_h": 11.7, "device_changed_24h": 0, "n_pay_1h": 0, "sum_1h": 0,
             "fan_out_1h": 0, "night_flag": 0}
    out = story_mod.breakin_rows(load_baseline(), feats)
    assert [r["id"] for r in out["rows"]] == ["R1", "R2", "R3", "R4", "R5", "R6"] and not any(r["fired"] for r in out["rows"])
    near = out["closest_call"]
    assert near["id"] == "R1" and near["actual"] == "9.97× usual" and "at least 10×" in near["needed"]
    feats["amount_ratio_30d"] = 1.0                                    # nothing is close any more
    assert story_mod.breakin_rows(load_baseline(), feats)["closest_call"] is None


def test_resistance_text_matches_the_numbers(store, ctx):
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=store)
    c = store.get_patch(pid)["story"]["chapters"]
    assert "step 3" in c["resistance"]["text"] and "frozen" in c["resistance"]["text"] and "₹1.00" in c["resistance"]["text"]
    assert "10 of 10 were stopped" in c["resistance"]["variants"]
    assert c["fix"]["plain"] == "Hold the payment for a check when it is night (00:00 to 05:00)."
    assert "pauses the payment" in c["fix"]["means"]


def test_a_partial_fix_is_described_honestly():
    story = {"loss_before": 500, "loss_after": 200, "new_rule": {"catch": {"n": 2, "what": "Victim account pays ₹3.00"}}}
    assert "still gets through" in story_mod.resistance_text(story, {})["text"] and "partly works" in story_mod.resistance_text(story, {})["text"]
    none = {"loss_before": 500, "loss_after": 500, "new_rule": {"catch": None}}
    assert "does not stop any step" in story_mod.resistance_text(none, {})["text"]

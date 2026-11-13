# Owner: M3. Golden cases, export/split leakage asserts, training, mined rules and candidates.
import pandas as pd
import pytest

from fa.config import load_config
from fa.contracts import FEATURES, Cond, Rule, RuleSet
from fa.core.engine import evaluate
from fa.core.features import compute_features
from fa.core.state import apply, new_state
from fa.ml import export, mine_rules
from fa.ml.split import feature_matrix, leave_one_playbook_out, time_account_split
from fa.ml.train import train_tree, train_xgboost
from fa.ml.report import report, to_markdown
from fa.world.generator import build_world, load_params
from fa.world.golden import golden_cases

SMALL = {**load_params(), "customers": 150, "sandbox_victims": 6, "sandbox_mules": 4,
         "history_days": 30, "validation_days": 7, "holdout_days": 7, "merchants": 50}
EP = {**load_config().section("ml")["export"], "plans_per_playbook": 40}


@pytest.fixture(scope="module")
def table():
    world = build_world(seed=3, params=dict(SMALL))
    rows = export._normal_rows(world, EP["split_days"]) + export._attack_rows(3, EP)
    from fa.contracts import FEATURES as F
    return pd.DataFrame(rows)[list(F) + list(export.LABEL_COLS) + list(export.META_COLS)]


def test_golden_cases_200_and_all_allowed_by_v1():
    from fa.rules.loader import load
    cases = golden_cases()
    assert len(cases) == 200 and golden_cases() == cases      # deterministic
    rs = load("v1")
    for case in cases:
        state = new_state()
        for ev in case:
            action, fired = evaluate(compute_features(state, ev), rs.rules)
            assert action == "allow", (ev, fired)
            apply(state, ev, action)


def test_export_columns_and_labels(table):
    assert set(table["label_fraud"]) == {0, 1}
    assert (table.loc[table["source"] == "normal", "label_fraud"] == 0).all()
    assert (table.loc[table["source"] == "attack", "label_fraud"] == 1).all()
    assert {"P1", "P2", "P3"} <= set(table["playbook"])


def test_labels_never_in_X(table):
    X = feature_matrix(table)
    assert list(X.columns) == list(FEATURES)
    assert not ({"label_fraud", "label_tag", "playbook", "source"} & set(X.columns))


def test_split_one_account_one_split_and_time_order(table):
    sp = time_account_split(table)
    assert sum(len(v) for v in sp.values()) == len(table)
    assert sp["train"].loc[sp["train"]["source"] == "normal", "day"].max() < sp["val"].loc[sp["val"]["source"] == "normal", "day"].min()
    assert sp["val"].loc[sp["val"]["source"] == "normal", "day"].max() < sp["test"].loc[sp["test"]["source"] == "normal", "day"].min()


def test_leave_one_playbook_out_hides_playbook(table):
    lo = leave_one_playbook_out(table, "P2")
    assert not (lo["train"]["playbook"] == "P2").any() and not (lo["val"]["playbook"] == "P2").any()
    assert (lo["heldout_attacks"]["playbook"] == "P2").all() and len(lo["heldout_attacks"]) > 0


def test_models_train_and_report(table):
    ml = load_config().section("ml")
    sp = time_account_split(table)
    for model in (train_tree(sp["train"], ml["tree"]), train_xgboost(sp["train"], ml["xgboost"])):
        res = report(model, {"val": sp["val"]})
        m = res["val"]
        assert 0 <= m["fpr"] <= 1 and m["recall"] > 0.5 and "precision" in m
    assert "| experiment |" in to_markdown({"x": {"tree": res}})


def test_tree_leaf_rules_are_valid_rules(table):
    ml = load_config().section("ml")
    tree = train_tree(time_account_split(table)["train"], ml["tree"])
    leaves = mine_rules._leaf_rules(tree, 0.5, 5)
    assert leaves
    for leaf in leaves:
        assert 1 <= len(leaf["conds"]) <= 4
        Rule(id="x", action="hold", when=[Cond(**c) for c in leaf["conds"]])   # contract validation


def test_merge_keeps_tightest_bound():
    got = mine_rules._merge([{"f": "n_pay_1h", "op": ">", "v": 1}, {"f": "n_pay_1h", "op": ">", "v": 3},
                             {"f": "sum_1h", "op": "<=", "v": 9}, {"f": "sum_1h", "op": "<=", "v": 5}])
    assert {(c["f"], c["op"], c["v"]) for c in got} == {("n_pay_1h", ">", 3), ("sum_1h", "<=", 5)}


def test_candidates_stop_the_attack_with_valid_conditions():
    from fa.agents.search import worst_case
    from fa.rules.loader import load
    rs = load("v1")
    trace = worst_case("P2", rs, 15, 1)
    assert trace.loss_through > 0
    cands = mine_rules.candidates(trace, rs)
    assert cands
    for c in cands:
        assert 1 <= len(c["conds"]) <= 2 and c["stopped_loss"] > 0 and c["added_fpr_pp"] >= 0
        assert all(x["f"] in FEATURES and x["op"] in ("<", "<=", ">", ">=", "==") for x in c["conds"])
        assert {"missed_step", "target_step", "val_payments"} <= set(c["evidence"])
    keys = [(-c["stopped_loss"], c["added_fpr_pp"], len(c["conds"])) for c in cands]
    assert keys == sorted(keys)


def test_candidates_empty_when_nothing_missed():
    from fa.contracts import Trace
    from fa.rules.loader import load
    assert mine_rules.candidates(Trace(plan_id="p", steps=[], loss_through=0, missed_step=None), load("v1")) == []


def test_percentile_mode_singles_only(monkeypatch):
    from fa.agents.search import worst_case
    from fa.rules.loader import load
    monkeypatch.setenv("ML_MODE", "percentile")
    rs = load("v1")
    trace = worst_case("P2", rs, 10, 1)
    assert all(len(c["conds"]) == 1 for c in mine_rules.candidates(trace, rs))
    assert isinstance(mine_rules.baseline_ruleset(), RuleSet)


# ---- saved models + cards (need `python -m fa.ml.report`; skipped on a clean checkout) -------------
import hashlib
import json
from pathlib import Path

MODELS = Path("data/ml/models")
CARD_KEYS = {"seed", "split_names", "features", "metrics", "training_table", "created_at"}
needs_models = pytest.mark.skipif(not (MODELS / "xgboost.joblib").exists() or not Path("data/ml/results.json").exists(),
                                  reason="run python -m fa.ml.report first")


def test_load_model_missing_gives_clear_error(tmp_path):
    from fa.ml import load_model
    with pytest.raises(FileNotFoundError, match="fa.ml.report"):
        load_model("decision_tree", model_dir=tmp_path)
    with pytest.raises(ValueError):
        load_model("nope")


def test_save_models_roundtrip(table, tmp_path):
    """save_models writes joblib + card + leaves text; load_model reads them back."""
    import json as j
    from fa.ml import load_model
    from fa.ml.report import save_models

    ml = load_config().section("ml")
    sp = time_account_split(table)
    models = {"tree": train_tree(sp["train"], ml["tree"]), "xgboost": train_xgboost(sp["train"], ml["xgboost"])}
    results = {"time+account split": {k: report(m, {"val": sp["val"]}) for k, m in models.items()}}
    tp = tmp_path / "t.parquet"
    table.to_parquet(tp)
    save_models(models, results, tp, len(table), 3, tmp_path)
    assert (tmp_path / "models" / "decision_tree_leaves.txt").read_text().strip()
    for name in ("decision_tree", "xgboost"):
        model, card = load_model(name, model_dir=tmp_path / "models")
        assert CARD_KEYS <= set(card) and card["training_table"]["rows"] == len(table)
        assert card["training_table"]["sha256"] == hashlib.sha256(tp.read_bytes()).hexdigest()
        assert hasattr(model, "predict_proba")


@needs_models
def test_saved_cards_match_table_and_results():
    from fa.ml import load_model
    results = json.loads(Path("data/ml/results.json").read_text())
    for name, key in (("decision_tree", "tree"), ("xgboost", "xgboost")):
        model, card = load_model(name)
        assert CARD_KEYS <= set(card)
        assert list(card["features"]) == list(FEATURES)
        tp = Path(card["training_table"]["path"])
        assert card["training_table"]["sha256"] == hashlib.sha256(tp.read_bytes()).hexdigest()
        assert card["training_table"]["rows"] == len(pd.read_parquet(tp))
        assert card["metrics"] == {exp: splits[key] for exp, splits in results.items()}
        assert any(e.startswith("leave out") for e in card["metrics"]) and "time+account split" in card["metrics"]


def test_models_not_in_live_path():
    """Attacker, defender and verifier gates must not load or call ML models."""
    import re
    for pkg in ("fa/agents", "fa/verify", "fa/plans", "fa/release", "fa/core"):
        for f in Path(pkg).rglob("*.py"):
            src = f.read_text(encoding="utf-8")
            assert not re.search(r"load_model|joblib|xgboost|sklearn|fa\.ml\.(train|report|models)", src), f


def test_active_v1_is_hand_written_baseline():
    from fa.rules.loader import load
    rs = load("v1")
    assert [r.id for r in rs.rules] == ["R1", "R2", "R3", "R4", "R5", "R6"]
    assert all(r.source == "hand" for r in rs.rules)

# Owner: M3. The Kaggle pipeline (kaggle/): schema detection, SQL features == fa.core.features, labelling, train/export.
# Runs on FAKE RBIH-shaped data from kaggle/make_fixture.py; the real dataset is never used or stored here.
import os
import sys

import pytest

duckdb = pytest.importorskip("duckdb")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "kaggle"))

from make_fixture import make  # noqa: E402
from rbih_common import prepare  # noqa: E402
from rbih_config import Config, SchemaError, resolve_columns  # noqa: E402
from rbih_features import FEATURES, build_features  # noqa: E402

from fa.core.features import compute_features  # noqa: E402
from fa.core.state import apply, new_state  # noqa: E402


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    root = tmp_path_factory.mktemp("rbih")
    fx = str(root / "FAKE")
    make(fx, n_legit=30, n_mule=4, n_unlabelled=3, days=100, seed=3)
    cfg = Config(input_dir=fx, out_dir=str(root / "out"), work_dir=str(root / "work"), legit_account_frac=1.0,
                 memory_limit="2GB", threads=2)
    ctx = prepare(cfg)
    info = build_features(cfg, ctx)
    return cfg, ctx, info


def test_columns_detected_and_ambiguity_is_loud(pipeline):
    _, ctx, _ = pipeline
    assert ctx["mapping"]["txn"]["account"] == "ACCOUNT_ID" and ctx["mapping"]["labels"]["is_mule"] == "IS_MULE"
    with pytest.raises(SchemaError, match="Columns present"):
        resolve_columns(["foo", "bar"], {"account": [r"^acct"], "ts": [r"time"]}, {}, "txn table", ("account", "ts"))


def test_sql_features_match_python_reference(pipeline):
    """Sender-side features == compute_features(payment); receiving-side == compute_features(cashout)."""
    cfg, ctx, _ = pipeline
    con = ctx["con"]
    sql = {r[0]: r[1:] for r in con.execute(f"SELECT rid, {', '.join(FEATURES)} FROM feat").fetchall()}
    rows = con.execute("SELECT rid, acct, ts, amt, cp, dir FROM base ORDER BY acct, ts, rid").fetchall()
    state, cur, checked = None, None, 0
    for rid, acct, ts, amt, cp, d in rows:
        if acct != cur:
            state, cur = new_state(), acct
        paise = int(round(amt))
        if d == "C":
            state.inflows.setdefault(acct, []).append((ts, cp, paise))
            continue
        pay = {"event_id": str(rid), "ts": ts, "type": "payment", "account": acct, "payee": cp, "device": None, "amount": paise}
        fp = compute_features(state, pay)
        fc = compute_features(state, {**pay, "type": "cashout", "payee": None})
        apply(state, pay, "allow")
        if rid not in sql:
            continue
        want = dict(fp)
        want["r_fan_in_24h"], want["r_passthrough_1h"] = fc["r_fan_in_24h"], fc["r_passthrough_1h"]
        got = dict(zip(FEATURES, sql[rid]))
        for k in FEATURES:
            assert got[k] == pytest.approx(want[k], rel=1e-6, abs=1e-6), (rid, k, got[k], want[k])
        checked += 1
    assert checked > 500


def test_labels_have_no_leakage(pipeline):
    cfg, ctx, info = pipeline
    con, W = ctx["con"], cfg.mule_window_days * 86400
    assert con.execute("SELECT count(*) FROM feat f JOIN base b USING (rid) WHERE b.is_mule = 1 AND b.ts > b.wend").fetchone()[0] == 0
    assert con.execute(f"SELECT count(*) FROM feat f JOIN base b USING (rid) WHERE f.y = 1 AND b.ts < b.wend - {W}").fetchone()[0] == 0
    assert con.execute("SELECT count(*) FROM feat WHERE y = 1 AND is_mule = 0").fetchone()[0] == 0
    assert info["rows_positive"] > 20 and info["accounts_kept"]["mule"] == 4
    # an account lives in exactly one split
    assert con.execute("SELECT count(*) FROM (SELECT acct FROM feat GROUP BY acct HAVING count(DISTINCT split) > 1)").fetchone()[0] == 0


def test_train_export_and_reasons(pipeline, tmp_path):
    """Whole stage 2 on fake data: artifacts written, hashes match, no rows exported, reasons are plain text."""
    import json
    import re

    import numpy as np
    from rbih_explain import explain_rows
    from rbih_export import export
    from rbih_train import train_all

    cfg, ctx, info = pipeline
    cfg = Config(**{**cfg.__dict__, "out_dir": str(tmp_path / "art"), "use_gpu": "no"})
    result = train_all(cfg, ctx["con"])
    out = export(result, info, ctx, cfg)
    assert {"model.json", "model_card.json", "friction_tables.json", "mined_rules.json", "metrics.json"} <= set(out["files"])

    card = json.load(open(tmp_path / "art" / "model_card.json"))
    import hashlib
    for name, digest in card["sha256"].items():
        assert hashlib.sha256((tmp_path / "art" / name).read_bytes()).hexdigest() == digest
    assert "CC BY-NC-SA" in card["dataset"] and card["limits"]

    ft = json.load(open(tmp_path / "art" / "friction_tables.json"))["tables"]
    assert "payee_age_h" in ft and all("legit_flagged_pct_test" in r for r in ft["r_fan_in_24h"])
    for rule in json.load(open(tmp_path / "art" / "mined_rules.json")):
        assert 1 <= len(rule["when"]) <= 4 and all(c["f"] in FEATURES for c in rule["when"])

    df = result["df"]
    top = df[df["y"] == 1].head(20)
    reasons = explain_rows(result["xgboost"].get_booster(), top, list(FEATURES), top=3)
    assert any(reasons)
    for r in (x for rs in reasons for x in rs):
        assert not re.search(r"_(1h|24h|30d|h)\b|ratio_", r["text"]), r["text"]    # no raw feature names leak to users
        assert r["push"] > 0
    assert np.isfinite(result["scores"]["xgboost"]).all()

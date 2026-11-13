"""Owner: M3. The contract test (docs/PLAN_IMPLEMENTATION.pdf M3-B): run the
real Kaggle exporter on the fixture, then load the result with the app's
bundle loader. If either side drifts from the contract, this fails.
"""
from __future__ import annotations

import os
import sys

import pytest

duckdb = pytest.importorskip("duckdb")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "kaggle"))

from fa.rbih.bundle import REQUIRED_FILES, load_bundle, verify


@pytest.fixture(scope="module")
def rehearsal_bundle(tmp_path_factory):
    from make_fixture import make
    from rbih_common import prepare
    from rbih_config import Config
    from rbih_export import export
    from rbih_features import build_features
    from rbih_train import train_all

    root = tmp_path_factory.mktemp("rbih_contract")
    fx = str(root / "FAKE")
    make(fx, n_legit=30, n_mule=4, n_unlabelled=3, days=100, seed=5)
    cfg = Config(
        input_dir=fx, out_dir=str(root / "out"), work_dir=str(root / "work"),
        legit_account_frac=1.0, memory_limit="2GB", threads=2, use_gpu="no", rehearsal=True,
    )
    ctx = prepare(cfg)
    info = build_features(cfg, ctx)
    result = train_all(cfg, ctx["con"])
    export(result, info, ctx, cfg)
    return cfg.out_dir


def test_real_exporter_output_passes_the_app_loader(rehearsal_bundle):
    problems = verify(rehearsal_bundle)
    assert problems == [], problems


def test_verified_bundle_loads_and_is_marked_rehearsal(rehearsal_bundle):
    verify(rehearsal_bundle)  # precondition for load_bundle; not re-checked below
    loaded = load_bundle(rehearsal_bundle)
    assert loaded["model_card"]["rehearsal"] is True
    assert loaded["model_card"]["schema_version"] == "1.0"
    assert "model_path" in loaded  # use_gpu="no" still writes model.json


def test_verify_catches_a_tampered_file(rehearsal_bundle, tmp_path):
    import shutil

    tampered = tmp_path / "tampered"
    shutil.copytree(rehearsal_bundle, tampered)
    (tampered / "metrics.json").write_text('{"tampered": true}', encoding="utf-8")

    problems = verify(tampered)
    assert any("sha256 mismatch" in p for p in problems)


def test_verify_catches_a_missing_required_file(rehearsal_bundle, tmp_path):
    import shutil

    broken = tmp_path / "broken"
    shutil.copytree(rehearsal_bundle, broken)
    (broken / "feature_spec.json").unlink()

    problems = verify(broken)
    assert any("feature_spec.json" in p and "missing" in p for p in problems)


def test_verify_rejects_a_wrong_schema_version(rehearsal_bundle, tmp_path):
    import json
    import shutil

    wrong = tmp_path / "wrong_schema"
    shutil.copytree(rehearsal_bundle, wrong)
    card_path = wrong / "model_card.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card["schema_version"] = "9.9"
    card_path.write_text(json.dumps(card), encoding="utf-8")

    problems = verify(wrong)
    assert any("schema_version" in p for p in problems)


def test_all_required_files_are_hash_verified_in_a_real_bundle(rehearsal_bundle):
    import json

    card = json.loads((open(f"{rehearsal_bundle}/model_card.json", encoding="utf-8")).read())
    for name in REQUIRED_FILES:
        if name != "model_card.json":
            assert name in card["sha256"], f"{name} must be hash-verified by model_card.sha256"

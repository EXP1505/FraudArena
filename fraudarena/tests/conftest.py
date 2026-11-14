"""Owner: M1. Shared fixtures — only loads params.yaml. No other shared
conftest.py files; each owner's tests/test_*.py is otherwise self-contained.
"""
from __future__ import annotations

import os
import tempfile

import pytest

# Tests must never write to the real database: before this, every run appended TEST_ACTION, "x",
# rollback and world_reset rows to data/fraudarena.db, so the ledger shown in the dashboard was
# test noise. api.db reads DATABASE_URL at connect time, so set it before anything connects.
_T = tempfile.mkdtemp(prefix="fa-test-")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_T, "test.db")
# Same for the file stores: a test that calls POST /api/world/reset used to wipe the real patches.
os.environ["FA_RULES_STORE"] = os.path.join(_T, "rule_versions")
os.environ["FA_REGRESSION_PATH"] = os.path.join(_T, "regression_plans.json")
# Tests pin the hand-written baseline whatever RBIH bundle is installed locally.
os.environ.setdefault("FA_BASELINE", "hand")
os.environ["FA_NO_DOTENV"] = "1"          # tests never read the real .env (it may hold a live key)
os.environ["FA_NOFIX_PATH"] = os.path.join(_T, "nofix_reports.json")
os.environ["FA_CREDITS_PATH"] = os.path.join(_T, "credits.json")
os.environ["FA_INVENTED_PATH"] = os.path.join(_T, "invented_playbooks.json")
os.environ["FA_SNAPSHOT_DIR"] = os.path.join(_T, "snapshots")

from fa.config import load_config


@pytest.fixture(scope="session")
def config():
    return load_config()


@pytest.fixture(scope="session")
def params(config):
    return config.params

"""Owner: M1. Shared fixtures — only loads params.yaml. No other shared
conftest.py files; each owner's tests/test_*.py is otherwise self-contained.
"""
from __future__ import annotations

import pytest

from fa.config import load_config


@pytest.fixture(scope="session")
def config():
    return load_config()


@pytest.fixture(scope="session")
def params(config):
    return config.params

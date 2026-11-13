"""Owner: M1. Test 10: POST /tx returns the same decision as calling
fa.core.engine.decide directly; plus the CP1 gate script's three events.
"""
from __future__ import annotations

import pytest


@pytest.mark.skip(reason="M1-11: written once M2's /tx and M4's decide() land")
def test_tx_matches_engine_decide():
    raise NotImplementedError

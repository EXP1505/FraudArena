"""Owner: M2. Tamper test: editing one field in a stored ledger row must be
caught by fa.ledger.verify.verify() at that row's seq.
"""
from __future__ import annotations

import pytest


@pytest.mark.skip(reason="M2-07: written with fa.ledger.chain/verify")
def test_tamper_detected_at_edited_row():
    raise NotImplementedError

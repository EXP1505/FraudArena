"""Owner: M3. Split by time (train days 1-30, val 31-37, test 38-44), by
account (a sandbox account appears in exactly one split), leave-one-playbook-out.
Must assert label columns are not present in X."""
from __future__ import annotations

import pandas as pd


def time_account_split(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    raise NotImplementedError


def leave_one_playbook_out(df: pd.DataFrame, playbook: str) -> dict[str, pd.DataFrame]:
    raise NotImplementedError

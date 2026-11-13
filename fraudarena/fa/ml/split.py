"""Owner: M3. Split by time (train days 1-30, val 31-37, test 38-44), by
account (a sandbox account appears in exactly one split), leave-one-playbook-out.
Must assert label columns are not present in X."""
from __future__ import annotations

import pandas as pd

from fa.contracts import FEATURES
from fa.ml.export import LABEL_COLS, META_COLS

SPLITS = ("train", "val", "test")


def feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """X for any model: exactly FEATURES, with a hard leakage assert."""
    X = df[list(FEATURES)]
    assert not (set(X.columns) & (set(LABEL_COLS) | set(META_COLS))), "label/meta column leaked into X"
    return X


def labels(df: pd.DataFrame) -> pd.Series:
    return df["label_fraud"]


def time_account_split(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Normal rows split by day, attack rows by account (one account -> one split)."""
    out = {s: df[df["time_split"] == s].reset_index(drop=True) for s in SPLITS}
    accts = {s: set(out[s].loc[out[s]["source"] == "attack", "account"]) for s in SPLITS}
    for a in SPLITS:
        for b in SPLITS:
            if a < b:
                assert not (accts[a] & accts[b]), f"attack account in two splits: {a}/{b}"
    for s in SPLITS:
        feature_matrix(out[s])
    return out


def leave_one_playbook_out(df: pd.DataFrame, playbook: str) -> dict[str, pd.DataFrame]:
    """Train never sees ``playbook``. test = held-out attacks + normal test days;
    heldout_attacks = every row of that playbook (the generalisation number)."""
    held = df["playbook"] == playbook
    base = time_account_split(df[~held].reset_index(drop=True))
    test = pd.concat([base["test"], df[held & (df["time_split"] == "test")]], ignore_index=True)
    out = {"train": base["train"], "val": base["val"], "test": test,
           "heldout_attacks": df[held].reset_index(drop=True)}
    assert not (out["train"]["playbook"] == playbook).any()
    return out

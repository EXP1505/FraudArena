"""Owner: M3. precision, recall, FPR, PR-AUC, P@100 per split -> a results
table (markdown + JSON). Anything above 0.99 is investigated as a leakage bug."""
from __future__ import annotations

import pandas as pd


def report(model, splits: dict[str, pd.DataFrame]) -> dict:
    raise NotImplementedError

"""Owner: M3. Trains a DecisionTree (params.yaml ml.tree) and an XGBoost
model (params.yaml ml.xgboost). No hyperparameter tuning."""
from __future__ import annotations

import pandas as pd


def train_tree(train_df: pd.DataFrame, params: dict):
    raise NotImplementedError


def train_xgboost(train_df: pd.DataFrame, params: dict):
    raise NotImplementedError

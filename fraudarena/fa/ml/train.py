"""Owner: M3. Trains a DecisionTree (params.yaml ml.tree) and an XGBoost
model (params.yaml ml.xgboost). No hyperparameter tuning."""
from __future__ import annotations

import pandas as pd

from fa.ml.split import feature_matrix, labels


def train_tree(train_df: pd.DataFrame, params: dict):
    from sklearn.tree import DecisionTreeClassifier

    X, y = feature_matrix(train_df), labels(train_df)
    return DecisionTreeClassifier(max_depth=params["max_depth"], min_samples_leaf=params["min_samples_leaf"],
                                  class_weight="balanced", random_state=params["random_state"]).fit(X, y)


def train_xgboost(train_df: pd.DataFrame, params: dict):
    from xgboost import XGBClassifier

    X, y = feature_matrix(train_df), labels(train_df)
    pos = max(int(y.sum()), 1)
    return XGBClassifier(n_estimators=params["n_estimators"], max_depth=params["max_depth"],
                         learning_rate=params["learning_rate"], random_state=params["random_state"],
                         scale_pos_weight=(len(y) - pos) / pos, n_jobs=1, eval_metric="logloss").fit(X, y)

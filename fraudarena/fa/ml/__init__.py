"""M3 machine-learning package.

LIVE-PATH POLICY: no model in this package is called by the attacker, the defender or the verifier
gates. The decision tree's leaves become JSON rules (fa.ml.mine_rules); those rules reach the system
only as proposed patches and must pass gates G1-G6 like any other patch. XGBoost is a comparison
baseline only. The active v1 is the hand-written R1-R6 in fa/rules/baseline_v1.json.
"""
from fa.ml.models import load_model

__all__ = ["load_model"]

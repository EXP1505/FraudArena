"""Owner: M3. Replay the world through compute_features/apply and write a
parquet file (one row per payment) with labels in separate columns. Attack
rows = 300 random plans per playbook vs an allow-all rule set, via
fa.plans.executor.execute."""
from __future__ import annotations

from pathlib import Path


def export_training_table(seed: int, out_path: Path) -> Path:
    raise NotImplementedError

"""Owner: M3. Replay the world through compute_features/apply and write a
parquet file (one row per payment) with labels in separate columns. Attack
rows = plans_per_playbook random plans per playbook vs an allow-all rule set,
via fa.plans.executor.execute.

Columns: FEATURES (the model inputs) | label_fraud, label_tag (labels, never
inputs) | meta: row_id, source (normal|attack), playbook, account, ts, day,
amount, time_split (train|val|test), account_split.

Normal rows: every payment in the world; look-alikes keep label_fraud = 0 (they
are benign by construction) and carry their tag in label_tag.
Attack rows: each plan runs from an allow-all rule set on a warm victim account
(realistic history, so amount_ratio_30d etc. are not trivially 1.0) at a random
time of day; every money step is one row. One attack account per plan, so a
sandbox account lives in exactly one split.
"""
from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

from fa.config import load_config
from fa.contracts import FEATURES, RuleSet
from fa.core.clock import DAY, HOUR
from fa.core.snapshot import restore
from fa.world.generator import build_world, replay, sandbox_state

ALLOW_ALL = RuleSet(version="allow-all", rules=[])
LABEL_COLS = ("label_fraud", "label_tag")
META_COLS = ("row_id", "source", "playbook", "account", "ts", "day", "amount", "time_split", "account_split")
MONEY = {"pay", "payment", "cashout"}


def _export_params() -> dict:
    return load_config().section("ml")["export"]


def time_split_of_day(day: int, sd: dict) -> str:
    if day < sd["train"]:
        return "train"
    return "val" if day < sd["train"] + sd["val"] else "test"


def account_split_of(index: int) -> str:
    """Deterministic 60/20/20 by attack-account index."""
    r = index % 10
    return "train" if r < 6 else ("val" if r < 8 else "test")


warm_victim = sandbox_state


def _normal_rows(world: dict, sd: dict) -> list[dict]:
    rows = []
    for ev, feats, _ in replay(restore(world["state"]), world["events"]):
        if ev["type"] != "payment":
            continue
        day = ev["ts"] // DAY
        tag = world["labels"].get(ev["event_id"], "")
        rows.append({**feats, "label_fraud": 0, "label_tag": tag, "row_id": ev["event_id"], "source": "normal",
                     "playbook": "", "account": ev["account"], "ts": ev["ts"], "day": day,
                     "amount": ev["amount"], "time_split": time_split_of_day(day, sd), "account_split": ""})
    return rows


def _attack_rows(seed: int, ep: dict) -> list[dict]:
    from fa.plans.executor import execute
    from fa.plans.playbooks import PARAM_RANGES, build_plan

    rng = random.Random(seed)
    rows: list[dict] = []
    idx = 0
    for pb, ranges in PARAM_RANGES.items():
        for k in range(int(ep["plans_per_playbook"])):
            params = {n: rng.uniform(lo, hi) for n, (lo, hi) in ranges.items()}
            plan = build_plan(pb, params, seed=seed * 1000 + idx)  # type: ignore[arg-type]
            shift = rng.randrange(0, DAY)  # random time of day
            plan = plan.model_copy(update={"steps": [s.model_copy(update={"t": s.t + shift}) for s in plan.steps]})
            trace = execute(plan, warm_victim(ep), ALLOW_ALL)
            asplit = account_split_of(idx)
            acct = f"ATK-{pb}-{k:04d}"
            for j, (step, feats, _d) in enumerate(trace.steps):
                if step.act not in MONEY or not step.amount:
                    continue
                rows.append({**feats, "label_fraud": 1, "label_tag": pb, "row_id": f"{plan.plan_id}-s{j}",
                             "source": "attack", "playbook": pb, "account": acct, "ts": step.t,
                             "day": -1, "amount": step.amount, "time_split": asplit, "account_split": asplit})
            idx += 1
    return rows


def export_training_table(seed: int, out_path: Path) -> Path:
    ep = _export_params()
    world = build_world(seed)
    rows = _normal_rows(world, ep["split_days"]) + _attack_rows(seed, ep)
    df = pd.DataFrame(rows)[list(FEATURES) + list(LABEL_COLS) + list(META_COLS)]
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    return out_path


def load_table(seed: int | None = None, path: Path | None = None, refresh: bool = False) -> pd.DataFrame:
    seed = int(seed if seed is not None else load_config().section("common").get("seed", 42))
    path = Path(path or f"data/ml/training_table_s{seed}.parquet")
    if refresh or not path.exists():
        export_training_table(seed, path)
    return pd.read_parquet(path)


if __name__ == "__main__":
    s = int(load_config().section("common").get("seed", 42))
    d = load_table(s, refresh=True)
    print(d.shape, d.groupby(["source", "time_split"]).size().to_dict())

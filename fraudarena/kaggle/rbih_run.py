"""Command line / notebook entry point.

    python rbih_run.py inspect     # stage 1 (~10 min): writes schema_report.json
    python rbih_run.py train       # stage 2: features -> train -> export  (writes artifacts/rbih/)
    python rbih_run.py all
"""
from __future__ import annotations

import json
import sys

from rbih_config import CFG, Config


def run_train(cfg: Config = CFG) -> dict:
    from rbih_common import prepare
    from rbih_export import export
    from rbih_features import build_features
    from rbih_train import train_all

    ctx = prepare(cfg)
    info = build_features(cfg, ctx)
    print("features built:", json.dumps(info, default=str)[:600])
    result = train_all(cfg, ctx["con"])
    print("gpu used:", result["gpu_used"])
    print(json.dumps(result["metrics"]["xgboost"], indent=1, default=str)[:3000])
    if result["investigate_if_above_0.99"]:
        print("WARNING: scores above 0.99, investigate leakage:", result["investigate_if_above_0.99"])
    return export(result, info, ctx, cfg)


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "inspect"
    if stage in ("inspect", "all"):
        from rbih_inspect import inspect
        print(json.dumps(inspect(CFG), indent=1, default=str)[:4000])
    if stage in ("train", "all"):
        print(run_train(CFG))

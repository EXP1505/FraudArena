"""Owner: M4. Regression set: every plan that ever got loss > 0, with its seed.

Gate G3 replays all of them against a candidate rule set. Stored as JSON so the
set survives restarts. Module-level add()/all()/clear() use the default store
(env FA_REGRESSION_PATH, else data/regression_plans.json).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fa.contracts import Plan

_ROOT = Path(__file__).resolve().parents[2]


class RegressionStore:
    def __init__(self, path: str | os.PathLike | None = None) -> None:
        self.path = Path(path) if path else Path(
            os.environ.get("FA_REGRESSION_PATH", _ROOT / "data" / "regression_plans.json")
        )
        self._plans: list[Plan] | None = None

    def _load(self) -> list[Plan]:
        if self._plans is None:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8") or "[]")
                self._plans = [Plan.model_validate(p) for p in raw]
            else:
                self._plans = []
        return self._plans

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps([p.model_dump(mode="json") for p in self._load()], indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def add(self, plan: Plan) -> bool:
        """Add a plan; returns False if its plan_id is already stored."""
        plans = self._load()
        if any(p.plan_id == plan.plan_id for p in plans):
            return False
        plans.append(plan)
        self._save()
        return True

    def all(self) -> list[Plan]:
        return list(self._load())

    def clear(self) -> None:
        self._plans = []
        self._save()


_default: RegressionStore | None = None


def default_store() -> RegressionStore:
    global _default
    if _default is None:
        _default = RegressionStore()
    return _default


def add(plan: Plan) -> bool:
    return default_store().add(plan)


def all() -> list[Plan]:  # noqa: A001 - interface name fixed in docs/TIMELINE.md section 3
    return default_store().all()


def clear() -> None:
    default_store().clear()

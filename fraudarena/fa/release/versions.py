"""Owner: M4. Rule versions and patches (24h plan section 12).

Each rule-set version is stored once and never edited in place. The active
pointer moves atomically (write temp file, os.replace). Patches move through
PROPOSED -> VERIFIED | REJECTED -> AWAITING_APPROVAL -> ACTIVE | REJECTED.

Storage is JSON files under FA_RULES_STORE (default data/rule_versions/):
    versions/vN.json   patches/pt-N.json   active.json
so M4 does not depend on the database; M2 can mirror these into Postgres.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from fa.contracts import Rule, RuleSet

_ROOT = Path(__file__).resolve().parents[2]

PROPOSED = "PROPOSED"
VERIFIED = "VERIFIED"
AWAITING_APPROVAL = "AWAITING_APPROVAL"
ACTIVE = "ACTIVE"
REJECTED = "REJECTED"


class ReleaseError(Exception):
    """A release action is not allowed (wrong state, same person, unknown id...)."""


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _vnum(version: str) -> int:
    return int(version.lstrip("v"))


class VersionStore:
    def __init__(self, root: str | os.PathLike | None = None) -> None:
        self.root = Path(root) if root else Path(os.environ.get("FA_RULES_STORE", _ROOT / "data" / "rule_versions"))

    # ---- versions
    def _vpath(self, version: str) -> Path:
        return self.root / "versions" / f"{version}.json"

    def list_versions(self) -> list[str]:
        found = {p.stem for p in (self.root / "versions").glob("v*.json")} if (self.root / "versions").exists() else set()
        found.add("v1")
        return sorted(found, key=_vnum)

    def get(self, version: str) -> RuleSet:
        p = self._vpath(version)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            return RuleSet(version=data["version"], rules=[Rule.model_validate(r) for r in data["rules"]])
        if version == "v1":
            from fa.rules.loader import load_baseline

            return load_baseline()
        raise KeyError(f"unknown rule version {version!r}")

    def meta(self, version: str) -> dict:
        p = self._vpath(version)
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            return {k: d.get(k) for k in ("version", "parent", "created_at", "source", "patch_id")}
        return {"version": version, "parent": None, "created_at": None, "source": "baseline", "patch_id": None}

    def save(self, rs: RuleSet, parent: str | None, source: str, patch_id: str | None = None) -> None:
        """Store a new version. Refuses to overwrite an existing one."""
        if self._vpath(rs.version).exists() or rs.version == "v1":
            raise ReleaseError(f"version {rs.version} already exists; versions are never edited in place")
        _atomic_write(self._vpath(rs.version), {
            "version": rs.version, "parent": parent, "created_at": time.time(), "source": source,
            "patch_id": patch_id, "rules": [r.model_dump(mode="json") for r in rs.rules],
        })

    def next_version(self) -> str:
        return f"v{max(_vnum(v) for v in self.list_versions()) + 1}"

    # ---- active pointer
    def active_version(self) -> str:
        p = self.root / "active.json"
        return json.loads(p.read_text(encoding="utf-8"))["version"] if p.exists() else "v1"

    def set_active(self, version: str) -> None:
        if version not in self.list_versions():
            raise ReleaseError(f"cannot activate unknown version {version!r}")
        _atomic_write(self.root / "active.json", {"version": version})

    # ---- patches
    def _ppath(self, patch_id: str) -> Path:
        return self.root / "patches" / f"{patch_id}.json"

    def get_patch(self, patch_id: str) -> dict:
        p = self._ppath(patch_id)
        if not p.exists():
            raise KeyError(f"unknown patch {patch_id!r}")
        return json.loads(p.read_text(encoding="utf-8"))

    def save_patch(self, patch: dict) -> None:
        _atomic_write(self._ppath(patch["id"]), patch)

    def list_patches(self) -> list[dict]:
        d = self.root / "patches"
        if not d.exists():
            return []
        return sorted((json.loads(p.read_text(encoding="utf-8")) for p in d.glob("pt-*.json")),
                      key=lambda x: int(x["id"].split("-")[1]))

    def new_patch_id(self) -> str:
        nums = [int(p["id"].split("-")[1]) for p in self.list_patches()]
        return f"pt-{max(nums, default=0) + 1}"


_default: VersionStore | None = None


def default_store() -> VersionStore:
    global _default
    if _default is None:
        _default = VersionStore()
    return _default


def propose(rule: Rule, maker: str, *, starter: str | None = None, ctx: dict | None = None,
            store: VersionStore | None = None) -> str:
    """Create a PROPOSED patch and return its id.

    `starter` is the person who started the round (maker-checker: they cannot
    approve). If `ctx` is given, the patch is verified right away (gates +
    shadow). Without ctx it stays PROPOSED until verify_patch() is called; only
    an AWAITING_APPROVAL patch can be approved.
    """
    s = store or default_store()
    patch = {
        "id": s.new_patch_id(), "rule": rule.model_dump(mode="json"), "state": PROPOSED,
        "maker": maker, "starter": starter, "checker": None, "parent_version": s.active_version(),
        "new_version": None, "gates": None, "shadow": None, "reason": None,
        "created_at": time.time(), "ledger_seq": None,
    }
    s.save_patch(patch)
    if ctx is not None:
        verify_patch(patch["id"], ctx, store=s)
    return patch["id"]


def candidate_for(patch: dict, store: VersionStore) -> tuple[RuleSet, RuleSet]:
    """(active rule set, candidate = active + proposed rule under the next version)."""
    active = store.get(store.active_version())
    new_version = store.next_version()
    rule = Rule.model_validate(patch["rule"]).model_copy(update={"added_in": new_version})
    return active, RuleSet(version=new_version, rules=[*active.rules, rule])


def verify_patch(patch_id: str, ctx: dict, *, store: VersionStore | None = None) -> dict:
    """PROPOSED -> run G1..G6 -> VERIFIED (then shadow, AWAITING_APPROVAL) or REJECTED."""
    from fa.verify.gates import run_gates
    from fa.verify.shadow import compare

    s = store or default_store()
    patch = s.get_patch(patch_id)
    if patch["state"] != PROPOSED:
        raise ReleaseError(f"patch {patch_id} is {patch['state']}, expected {PROPOSED}")
    active, candidate = candidate_for(patch, s)
    results = run_gates(candidate, {**ctx, "base_rule_set": active})
    patch["gates"] = [r.model_dump(mode="json") for r in results]
    failed = [r for r in results if not r.passed]
    if failed:
        patch["state"] = REJECTED
        patch["reason"] = "; ".join(f"{r.gate}: {r.reason}" for r in failed)
    else:
        patch["state"] = VERIFIED
        patch["shadow"] = compare(active, candidate, ctx)
        patch["state"] = AWAITING_APPROVAL
    s.save_patch(patch)
    return patch

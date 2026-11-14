"""Owner: M4. Maker-checker approval (24h plan section 12).

AWAITING_APPROVAL -> ACTIVE (approve) or REJECTED (reject). The checker must be a
different person from the patch maker and from the person who started the round
(params.yaml release.require_different_checker). Approving stores the new rule
set as a new version, writes the ledger entry, then moves the active pointer
atomically. Nothing is edited in place.

The ledger is M2's fa.ledger.chain.append. Until it is implemented the call is
skipped and the patch records ledger_seq = None; pass `ledger=` to override.
"""
from __future__ import annotations

from typing import Callable

from fa.config import load_config
from fa.release.versions import (ACTIVE, AWAITING_APPROVAL, REJECTED, ReleaseError, VersionStore,
                                 candidate_for, default_store)

LedgerFn = Callable[[str, dict], object]


def default_ledger(action: str, payload: dict) -> int | None:
    """Append to M2's ledger; returns the sequence number, or None if M2's ledger
    is not implemented yet."""
    from fa.ledger import chain

    try:
        return chain.append(action, payload).seq
    except NotImplementedError:
        return None


def _seq(rec: object) -> int | None:
    return rec if isinstance(rec, int) or rec is None else getattr(rec, "seq", None)


def _norm(name: str | None) -> str:
    return (name or "").strip().casefold()


def _check_checker(patch: dict, checker: str) -> None:
    if not _norm(checker):
        raise ReleaseError("checker name is required")
    if load_config().section("release").get("require_different_checker", True):
        if _norm(checker) in {_norm(patch.get("maker")), _norm(patch.get("starter"))}:
            raise ReleaseError(f"checker {checker!r} must differ from the maker and the round starter")


def _require_awaiting(patch: dict) -> None:
    if patch["state"] != AWAITING_APPROVAL:
        raise ReleaseError(f"patch {patch['id']} is {patch['state']}, expected {AWAITING_APPROVAL}")


def approve(patch_id: str, checker: str, *, store: VersionStore | None = None,
            ledger: LedgerFn | None = None) -> dict:
    s = store or default_store()
    patch = s.get_patch(patch_id)
    _require_awaiting(patch)
    _check_checker(patch, checker)
    if patch["parent_version"] != s.active_version():
        raise ReleaseError(f"patch was built on {patch['parent_version']} but {s.active_version()} is active; re-propose")

    active, candidate = candidate_for(patch, s)
    gates = {g["gate"]: ("pass" if g["passed"] else "fail") for g in (patch["gates"] or [])}
    payload = {
        "from": active.version, "to": candidate.version, "patch_id": patch_id, "gates": gates,
        "metrics": _metrics(patch), "maker": patch["maker"], "checker": checker,
    }
    seq = _seq((ledger or default_ledger)("promote", payload))   # ledger first: a failure changes nothing
    s.save(candidate, parent=active.version, source="defender", patch_id=patch_id)
    s.set_active(candidate.version)
    if patch.get("plan"):                      # the attack this fix stops must stay stopped (gate G3 for later fixes)
        from fa.contracts import Plan
        from fa.verify import regression
        regression.add(Plan.model_validate(patch["plan"]))

    patch.update(state=ACTIVE, checker=checker, new_version=candidate.version, ledger_seq=seq)
    s.save_patch(patch)
    supersede_stale(store=s, ledger=ledger)
    return patch


def _sig(rule) -> tuple:
    return rule.action, frozenset((c.f, c.op, float(c.v)) for c in rule.when)


def supersede_stale(*, store: VersionStore | None = None, ledger: LedgerFn | None = None) -> list[str]:
    """Close proposals that can no longer be approved. A proposal is built on the rule set that was live when it was
    made; once another fix goes live it is out of date (approve() refuses it) and would sit in the "waiting" list for good.
    Each one is rejected by "system" with the reason, and the rejection is written to the ledger like any other."""
    from fa.contracts import Rule

    s = store or default_store()
    active_v = s.active_version()
    live = s.get(active_v).rules
    closed: list[str] = []
    for p in s.list_patches():
        if p["state"] != AWAITING_APPROVAL or p["parent_version"] == active_v:
            continue
        rule = Rule.model_validate(p["rule"])
        twin = next((r.id for r in live if _sig(r) == _sig(rule)), None)
        reason = f"Superseded: {active_v} went live after this was proposed" + (
            f", and the same rule is already live as {twin}." if twin else ". Run a new round if the weakness is still open.")
        seq = _seq((ledger or default_ledger)("reject", {"patch_id": p["id"], "maker": p["maker"], "checker": "system", "reason": reason}))
        p.update(state=REJECTED, checker="system", reason=reason, ledger_seq=seq)
        s.save_patch(p)
        closed.append(p["id"])
    return closed


def reject(patch_id: str, checker: str, reason: str = "", *, store: VersionStore | None = None,
           ledger: LedgerFn | None = None) -> dict:
    s = store or default_store()
    patch = s.get_patch(patch_id)
    _require_awaiting(patch)
    _check_checker(patch, checker)
    seq = _seq((ledger or default_ledger)("reject", {
        "patch_id": patch_id, "maker": patch["maker"], "checker": checker, "reason": reason,
    }))
    patch.update(state=REJECTED, checker=checker, reason=reason or "rejected by checker", ledger_seq=seq)
    s.save_patch(patch)
    return patch


def _metrics(patch: dict) -> dict:
    """Headline numbers from the shadow run, for the ledger record."""
    normal = (patch.get("shadow") or {}).get("normal") or {}
    return {"hold_rate_before": normal.get("base_rate"), "hold_rate_after": normal.get("cand_rate")}

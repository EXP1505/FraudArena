"""Owner: M4. Rollback: move the active pointer back to an earlier version.

Versions are never edited or deleted; rollback only moves the pointer (atomically)
and writes a ledger entry first, so a ledger failure changes nothing.
"""
from __future__ import annotations

from fa.release.approve import LedgerFn, _norm, _seq, default_ledger
from fa.release.versions import ReleaseError, VersionStore, default_store


def rollback(to_version: str, who: str, *, store: VersionStore | None = None,
             ledger: LedgerFn | None = None) -> dict:
    s = store or default_store()
    if not _norm(who):
        raise ReleaseError("a name is required to roll back")
    if to_version not in s.list_versions():
        raise ReleaseError(f"unknown version {to_version!r}")
    current = s.active_version()
    if to_version == current:
        raise ReleaseError(f"{to_version} is already active")
    seq = _seq((ledger or default_ledger)("rollback", {"from": current, "to": to_version, "who": who}))
    s.set_active(to_version)
    return {"from": current, "to": to_version, "who": who, "ledger_seq": seq}

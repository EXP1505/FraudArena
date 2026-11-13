"""Owner: M2/M4. Portable, signed rulebook and attack-library documents.

A document is plain JSON: {format, ..., sha256, public_key, signature}. `sha256` covers the canonical
JSON of everything except sha256/public_key/signature; `signature` is the ledger's Ed25519 key over that
hash, so a file downloaded today can be checked later (and on another machine, using the embedded
public key). No clock is read here: callers pass `exported_at`.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from fa.contracts import Rule
from fa.ledger.sign import load_or_create_key, sign

RULEBOOK_FORMAT = "fraudarena.rulebook/1"
ATTACKS_FORMAT = "fraudarena.attacks/1"
_SEAL = ("sha256", "public_key", "signature")


def canonical(doc: dict) -> bytes:
    body = {k: v for k, v in doc.items() if k not in _SEAL}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def public_key_hex(data_dir: str = "data") -> str:
    pub = load_or_create_key(data_dir).public_key()
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def seal(doc: dict, data_dir: str = "data") -> dict:
    """Return a copy with sha256, public_key and signature added."""
    digest = hashlib.sha256(canonical(doc)).hexdigest()
    return {**doc, "sha256": digest, "public_key": public_key_hex(data_dir),
            "signature": sign(digest.encode("utf-8"), data_dir)}


def check(doc: dict, data_dir: str = "data") -> dict:
    """authentic: content matches its hash AND the signature is valid for the embedded public key.
    this_server: that key is also this server's key. Never raises."""
    out = {"authentic": False, "this_server": False, "reason": ""}
    try:
        digest = hashlib.sha256(canonical(doc)).hexdigest()
        if doc.get("sha256") != digest:
            out["reason"] = "content was modified after it was exported (hash does not match)"
            return out
        if not doc.get("signature") or not doc.get("public_key"):
            out["reason"] = "file is not signed"
            return out
        pub = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(doc["public_key"]))
        pub.verify(bytes.fromhex(doc["signature"]), digest.encode("utf-8"))
        out.update(authentic=True, this_server=doc["public_key"] == public_key_hex(data_dir),
                   reason="signature valid")
    except Exception as exc:  # noqa: BLE001 - any parse/verify failure means not authentic
        out["reason"] = f"signature check failed ({type(exc).__name__})"
    return out


def parse_rules(doc: dict, max_rules: int = 20) -> list[Rule]:
    """Validate the rules of a rulebook document through the Rule contract (feature names, operators,
    at most 4 conditions). Raises ValueError for anything not acceptable."""
    if doc.get("format") != RULEBOOK_FORMAT:
        raise ValueError(f"unsupported format {doc.get('format')!r}, expected {RULEBOOK_FORMAT}")
    raw = doc.get("rules")
    if not isinstance(raw, list) or not raw:
        raise ValueError("rulebook has no rules")
    if len(raw) > max_rules:
        raise ValueError(f"too many rules ({len(raw)} > {max_rules})")
    rules = [Rule.model_validate(r) for r in raw]
    ids = [r.id for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate rule ids in file")
    return rules


def _cond(c: dict) -> str:
    return f"{c['f']} {c['op']} {c['v']}"


def to_csv(doc: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["version", "rule_id", "title", "action", "treatment", "conditions", "customer_message",
                "regulatory_basis", "legit_flagged_pct_test", "mule_flagged_pct_test"])
    for r in doc["rules"]:
        ev = r.get("evidence") or {}
        w.writerow([doc["version"], r["id"], r.get("title", ""), r["action"], r.get("treatment", ""),
                    " AND ".join(_cond(c) for c in r["when"]), r.get("customer_message", ""),
                    "; ".join(f"{x['instrument']} ({x['strength']})" for x in r.get("reg_refs") or []),
                    ev.get("legit_flagged_pct_test", ""), ev.get("mule_flagged_pct_test", "")])
    return buf.getvalue()


def to_markdown(doc: dict) -> str:
    src = doc.get("data_source", {})
    lines = [f"# FraudArena rulebook {doc['version']}", "",
             f"- Exported: {doc.get('exported_at', 'n/a')}",
             f"- Data source: {src.get('label', 'simulation')}",
             f"- Parent version: {doc.get('parent') or 'none (baseline)'}; created from: {doc.get('source', 'baseline')}",
             f"- SHA-256: `{doc.get('sha256', 'unsealed')}`", "",
             "Every rule below passed the automatic checks G1 to G6 and a second-person approval before it went live, "
             "except the starting rulebook, which is the baseline. Regulatory references are alignment notes, not a claim of compliance.", ""]
    for r in doc["rules"]:
        lines += [f"## {r['id']}: {r.get('title') or r['id']}", "",
                  f"- **Action:** {r.get('treatment') or r['action']}",
                  f"- **Fires when:** " + " AND ".join(f"`{_cond(c)}`" for c in r["when"]),
                  f"- **Customer sees:** \"{r.get('customer_message', '')}\"",
                  f"- **Why:** {r.get('rationale') or r.get('analyst_note', '')}"]
        for x in r.get("reg_refs") or []:
            lines.append(f"- **Basis ({x['strength']}):** {x['instrument']}: {x['note']}")
        ev = r.get("evidence") or {}
        if "legit_flagged_pct_test" in ev:
            lines.append(f"- **Evidence (test data):** honest customers held {ev['legit_flagged_pct_test']:.2f}%, "
                         f"mule accounts flagged {ev.get('mule_flagged_pct_test', 0):.2f}%")
        lines.append("")
    return "\n".join(lines)

"""Owner: M3 (Person A). Installer for the RBIH artifact bundle (docs/PLAN_IMPLEMENTATION.pdf section 4).

Usage:
    python -m fa.rbih.install [BUNDLE_PATH] [--dry-run] [--rehearsal] [--rollback]

Copies a verified bundle folder into data/rbih/current/ (with automatic rollback
backup in data/rbih/previous/), checks cryptographic integrity, and appends an
audit record to the ledger.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fa.rbih.bundle import BundleError, load_bundle, verify

CURRENT_DIR = Path("data/rbih/current")
PREVIOUS_DIR = Path("data/rbih/previous")
DEFAULT_BUNDLE = Path("artifacts/rbih")


def _safe_unzip(zip_path: Path, dest_dir: Path) -> Path:
    """Safely extract zip archive preventing directory traversal vulnerabilities."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.infolist():
            target_path = dest_dir / member.filename
            try:
                target_path.resolve().relative_to(dest_dir.resolve())
            except ValueError:
                raise BundleError([f"Malicious zip member detected with path traversal: {member.filename}"])
            z.extract(member, dest_dir)
    # If the zip contents were nested inside a single folder, unnest:
    extracted = [p for p in dest_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]
    if len(extracted) == 1 and not (dest_dir / "model_card.json").exists():
        return extracted[0]
    return dest_dir


def status(data_dir: Path | str | None = None) -> dict[str, Any]:
    """Return status dictionary matching the /api/model contract for Person B."""
    d = Path(data_dir or CURRENT_DIR)
    card_path = d / "model_card.json"
    if not d.is_dir() or not card_path.exists():
        return {
            "mode": "none",
            "dataset": "",
            "rehearsal": False,
            "verified": False,
            "metrics": {},
            "installed_at": None,
        }

    problems = verify(d)
    if problems:
        return {
            "mode": "invalid",
            "dataset": "",
            "rehearsal": False,
            "verified": False,
            "metrics": {},
            "problems": problems,
            "installed_at": None,
        }

    b = load_bundle(d)
    card = b["model_card"]
    metrics_file = b.get("metrics", {})
    metrics = metrics_file.get("metrics", {})
    xgb_test = metrics.get("xgboost", {}).get("test", {})

    pr_auc = xgb_test.get("pr_auc_weighted") or xgb_test.get("pr_auc")
    roc_auc = xgb_test.get("roc_auc_weighted") or xgb_test.get("roc_auc")
    at_friction = xgb_test.get("at_friction", {})
    f1pct = at_friction.get("1.000%") or at_friction.get("1.0%") or {}
    recall_1pct = f1pct.get("recall")

    # Install metadata if recorded
    meta_path = d / ".install_meta.json"
    installed_at = None
    if meta_path.exists():
        try:
            installed_at = json.loads(meta_path.read_text(encoding="utf-8")).get("installed_at")
        except Exception:
            pass
    if not installed_at:
        installed_at = card.get("created_at")

    mode = "rehearsal" if card.get("rehearsal") else "real"
    return {
        "mode": mode,
        "dataset": card.get("dataset", ""),
        "rehearsal": bool(card.get("rehearsal")),
        "verified": True,
        "metrics": {
            "pr_auc": pr_auc,
            "roc_auc": roc_auc,
            "recall_at_1pct": recall_1pct,
            "high_value_new_account_recall": xgb_test.get("recall_by_alert_reason_at_middle_friction", {})
            .get("High-Value Activity on New Account", {})
            .get("recall"),
        },
        "installed_at": installed_at,
    }


def rollback() -> dict[str, Any]:
    """Restore previous bundle from data/rbih/previous/."""
    if not PREVIOUS_DIR.exists():
        raise RuntimeError(f"Cannot rollback: {PREVIOUS_DIR} does not exist")

    # Swap back
    temp_dir = Path("data/rbih/temp_swap")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    if CURRENT_DIR.exists():
        CURRENT_DIR.rename(temp_dir)
    PREVIOUS_DIR.rename(CURRENT_DIR)
    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    # Log to ledger
    try:
        from fa.ledger.chain import append

        append("model_rollback", {"restored_to": str(CURRENT_DIR)})
    except Exception:
        pass

    return status()


def install(
    bundle_path: Path | str | None = None,
    dry_run: bool = False,
    rehearsal: bool = False,
    accept_high_auc: bool = False,
) -> dict[str, Any]:
    """Verify and install an artifact bundle into data/rbih/current/."""
    path = Path(bundle_path or DEFAULT_BUNDLE)
    if not path.exists():
        # Check if the user passed a rehearsal path that needs generating
        if rehearsal and str(path) in ("kaggle/fixture", "fixture"):
            from make_fixture import make
            from rbih_common import prepare
            from rbih_config import Config
            from rbih_export import export
            from rbih_features import build_features
            from rbih_train import train_all

            path.mkdir(parents=True, exist_ok=True)
            fx = str(path / "FAKE")
            make(fx, n_legit=30, n_mule=4, n_unlabelled=3, days=100, seed=5)
            cfg = Config(
                input_dir=fx,
                out_dir=str(path),
                work_dir=str(path / "work"),
                legit_account_frac=1.0,
                memory_limit="2GB",
                threads=2,
                use_gpu="no",
                rehearsal=True,
            )
            ctx = prepare(cfg)
            info = build_features(cfg, ctx)
            result = train_all(cfg, ctx["con"])
            export(result, info, ctx, cfg)
        else:
            raise FileNotFoundError(f"Bundle path not found: {path}")

    # Handle zip archive vs directory
    temp_extract = None
    if path.is_file() and path.suffix.lower() == ".zip":
        temp_extract = Path(tempfile.mkdtemp(prefix="rbih_bundle_"))
        bundle_dir = _safe_unzip(path, temp_extract)
    else:
        bundle_dir = path

    try:
        # Step 1: Verify contract
        problems = verify(bundle_dir)
        if problems:
            raise BundleError(problems)

        # Step 2: Check rehearsal mode gate
        b = load_bundle(bundle_dir)
        card = b["model_card"]
        is_rehearsal = bool(card.get("rehearsal"))
        if rehearsal and not is_rehearsal:
            raise BundleError(["--rehearsal flag provided, but model_card.rehearsal is False (refusing to install real bundle as rehearsal)"])
        if not rehearsal and is_rehearsal:
            raise BundleError(["model_card.rehearsal is True, but --rehearsal flag was not specified (refusing to install rehearsal bundle as real model)"])

        # Step 3: Check AUC sanity gate (leakage guard)
        metrics = b.get("metrics", {}).get("metrics", {})
        xgb_test = metrics.get("xgboost", {}).get("test", {})
        roc_auc = xgb_test.get("roc_auc_weighted") or xgb_test.get("roc_auc") or 0.0
        pr_auc = xgb_test.get("pr_auc_weighted") or xgb_test.get("pr_auc") or 0.0
        if (roc_auc > 0.99 or pr_auc > 0.99) and not accept_high_auc:
            raise BundleError([f"AUC above 0.99 (roc={roc_auc:.4f}, pr={pr_auc:.4f}); investigate possible leakage or pass --accept-high-auc"])

        if dry_run:
            return {
                "dry_run": True,
                "verified": True,
                "mode": "rehearsal" if is_rehearsal else "real",
                "dataset": card.get("dataset"),
                "files": list(b.keys()),
            }

        # Step 4: Atomic install
        CURRENT_DIR.parent.mkdir(parents=True, exist_ok=True)
        if CURRENT_DIR.exists():
            if PREVIOUS_DIR.exists():
                shutil.rmtree(PREVIOUS_DIR)
            shutil.copytree(CURRENT_DIR, PREVIOUS_DIR)
            shutil.rmtree(CURRENT_DIR)

        shutil.copytree(bundle_dir, CURRENT_DIR)

        # Record metadata
        meta = {
            "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mode": "rehearsal" if is_rehearsal else "real",
            "source": str(path),
            "bundle_sha256": card.get("sha256", {}),
        }
        (CURRENT_DIR / ".install_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        # Step 5: Append to ledger
        try:
            from fa.ledger.chain import append

            append(
                "model_installed",
                {
                    "mode": meta["mode"],
                    "dataset": card.get("dataset", ""),
                    "roc_auc": roc_auc,
                    "sha256": card.get("sha256", {}).get("model.json", ""),
                },
            )
        except Exception as e:
            # Non-blocking if running in lightweight test harness without db
            pass

        return status()
    finally:
        if temp_extract and temp_extract.exists():
            shutil.rmtree(temp_extract)


def main():
    parser = argparse.ArgumentParser(description="Install RBIH model bundle")
    parser.add_argument("bundle", nargs="?", default="artifacts/rbih", help="Path to bundle folder or zip archive")
    parser.add_argument("--dry-run", action="store_true", help="Validate bundle without installing")
    parser.add_argument("--rehearsal", action="store_true", help="Install a rehearsal bundle")
    parser.add_argument("--rollback", action="store_true", help="Restore previously installed bundle")
    parser.add_argument("--accept-high-auc", action="store_true", help="Bypass >0.99 AUC leakage gate")

    args = parser.parse_args()
    if args.rollback:
        res = rollback()
        print("Rollback successful:", json.dumps(res, indent=2))
        return

    res = install(
        args.bundle,
        dry_run=args.dry_run,
        rehearsal=args.rehearsal,
        accept_high_auc=args.accept_high_auc,
    )
    print("Bundle install status:", json.dumps(res, indent=2))


if __name__ == "__main__":
    main()

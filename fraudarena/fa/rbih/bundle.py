"""Owner: M3. The contract between Kaggle and the app (docs/PLAN_IMPLEMENTATION.pdf
section 3): pydantic models for model_card.json, and verify() that checks
hashes, schema version and feature order before anything else trusts a
bundle folder.

Strictly required (install refused if missing or invalid): model_card.json,
metrics.json, feature_spec.json. Everything else degrades a capability, not
the install: no model.json -> scorer returns None; no friction_tables.json
-> thresholds fall back to params.yaml, labelled "simulation"; no
mined_rules.json / schema_used.json -> simply skipped.

Nothing here reads data/rbih/current/ directly except through this module;
fa.rbih.resolver and fa.rbih.scorer always go through load_bundle().
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from fa.contracts import FEATURES

SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0"})

REQUIRED_FILES = ("model_card.json", "metrics.json", "feature_spec.json")
OPTIONAL_FILES = ("model.json", "friction_tables.json", "mined_rules.json", "schema_used.json")
ALL_FILES = REQUIRED_FILES + OPTIONAL_FILES


class ModelCard(BaseModel):
    name: str
    schema_version: str
    rehearsal: bool
    created_at: str
    dataset: str
    labels: str = ""
    sampling: dict = Field(default_factory=dict)
    split: str = ""
    seed: int | None = None
    gpu_used: bool = False
    libraries: dict = Field(default_factory=dict)
    unavailable_features: list[str] = Field(default_factory=list)
    deck_numbers: dict = Field(default_factory=dict)
    limits: list[str] = Field(default_factory=list)
    sha256: dict[str, str] = Field(default_factory=dict)


class BundleError(Exception):
    """A bundle fails its contract. Carries every problem found, not just the first."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path, problems: list[str]) -> dict | None:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        problems.append(f"{path.name}: could not parse ({exc})")
        return None


def verify(bundle_dir: Path | str) -> list[str]:
    """Every problem found with the bundle at `bundle_dir`; [] means it is
    safe to install. Never raises -- the installer decides what a problem
    means (refuse, or degrade a capability)."""
    bundle_dir = Path(bundle_dir)
    problems: list[str] = []

    if not bundle_dir.is_dir():
        return [f"{bundle_dir}: not a directory"]

    for name in REQUIRED_FILES:
        if not (bundle_dir / name).exists():
            problems.append(f"{name}: required file is missing")

    card_raw = _load_json(bundle_dir / "model_card.json", problems)
    if card_raw is None:
        if "model_card.json: required file is missing" not in problems:
            problems.append("model_card.json: could not be read")
        return problems  # nothing else below is checkable without the card

    try:
        card = ModelCard.model_validate(card_raw)
    except Exception as exc:  # pydantic.ValidationError and friends
        problems.append(f"model_card.json: schema invalid ({exc})")
        return problems

    if card.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        problems.append(
            f"model_card.json: schema_version {card.schema_version!r} not in "
            f"{sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )

    for name, expected in card.sha256.items():
        path = bundle_dir / name
        if not path.exists():
            problems.append(f"{name}: listed in model_card.sha256 but missing")
            continue
        actual = _sha256(path)
        if actual != expected:
            problems.append(f"{name}: sha256 mismatch (bundle has been modified or is corrupt)")

    for name in REQUIRED_FILES:
        if name != "model_card.json" and name not in card.sha256:
            problems.append(f"{name}: required but not hash-verified by model_card.sha256")

    feature_spec = _load_json(bundle_dir / "feature_spec.json", problems)
    if feature_spec is not None:
        got = feature_spec.get("features")
        if got != list(FEATURES):
            problems.append(
                f"feature_spec.json: feature order {got!r} does not match fa.contracts.FEATURES"
            )
    elif "feature_spec.json: required file is missing" not in problems:
        problems.append("feature_spec.json: could not be read")

    metrics = _load_json(bundle_dir / "metrics.json", problems)
    if metrics is None and "metrics.json: required file is missing" not in problems:
        problems.append("metrics.json: could not be read")

    return problems


def load_bundle(bundle_dir: Path | str) -> dict[str, Any]:
    """Every present file's parsed JSON, keyed by filename (minus .json), plus
    "model_path" if model.json exists. Call verify() first; this does not
    re-check anything."""
    bundle_dir = Path(bundle_dir)
    out: dict[str, Any] = {}
    for name in ALL_FILES:
        path = bundle_dir / name
        if name == "model.json":
            if path.exists():
                out["model_path"] = str(path)
            continue
        if path.exists():
            with open(path, encoding="utf-8") as f:
                out[name.removesuffix(".json")] = json.load(f)
    return out

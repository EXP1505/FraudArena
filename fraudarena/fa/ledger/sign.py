"""Owner: M2. Ed25519 signing; the key is generated on first start and
stored under data/.
"""
from __future__ import annotations


def load_or_create_key(data_dir: str = "data") -> object:
    raise NotImplementedError


def sign(payload: bytes) -> str:
    raise NotImplementedError


def verify_signature(payload: bytes, sig: str) -> bool:
    raise NotImplementedError

"""Owner: M2. Ed25519 signing; the key is generated on first start and
stored under data/.
"""
from __future__ import annotations

import os
from pathlib import Path
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

_KEY_CACHE: ed25519.Ed25519PrivateKey | None = None
KEY_FILENAME = "ed25519_key.pem"


def load_or_create_key(data_dir: str = "data") -> ed25519.Ed25519PrivateKey:
    """Load existing private key from data_dir/ed25519_key.pem or create a new one."""
    global _KEY_CACHE
    if _KEY_CACHE is not None:
        return _KEY_CACHE

    dir_path = Path(data_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    key_path = dir_path / KEY_FILENAME

    if key_path.exists():
        pem_data = key_path.read_bytes()
        key = serialization.load_pem_private_key(pem_data, password=None)
        if not isinstance(key, ed25519.Ed25519PrivateKey):
            raise TypeError("Loaded key is not an Ed25519 private key")
        _KEY_CACHE = key
        return key

    key = ed25519.Ed25519PrivateKey.generate()
    pem_data = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path.write_bytes(pem_data)
    _KEY_CACHE = key
    return key


def sign(payload: bytes, data_dir: str = "data") -> str:
    """Sign payload with Ed25519 private key; return signature as hex string."""
    key = load_or_create_key(data_dir)
    sig_bytes = key.sign(payload)
    return sig_bytes.hex()


def verify_signature(payload: bytes, sig: str, data_dir: str = "data") -> bool:
    """Verify Ed25519 signature (hex string) for payload using the public key."""
    try:
        key = load_or_create_key(data_dir)
        pub = key.public_key()
        sig_bytes = bytes.fromhex(sig)
        pub.verify(sig_bytes, payload)
        return True
    except (InvalidSignature, ValueError, Exception):
        return False

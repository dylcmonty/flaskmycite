from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Any, Dict

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_CONTRACT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _private_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "private"


def _safe_contract_id(contract_id: str) -> str:
    token = (contract_id or "").strip()
    if not token or not _CONTRACT_ID_RE.fullmatch(token):
        raise ValueError("contract_id must match [A-Za-z0-9_-]{1,128}")
    return token


def _contract_key_path(contract_id: str) -> Path:
    return _private_dir() / "vault" / "contracts" / f"{contract_id}.key"


def ensure_contract_key(contract_id: str) -> bytes:
    safe_contract_id = _safe_contract_id(contract_id)
    key_path = _contract_key_path(safe_contract_id)
    key_path.parent.mkdir(parents=True, exist_ok=True)

    if key_path.exists() and key_path.is_file():
        encoded = key_path.read_text(encoding="utf-8").strip()
        key = base64.b64decode(encoded)
        if len(key) != 32:
            raise ValueError("Contract key file must decode to 32 bytes")
        return key

    key = os.urandom(32)
    key_path.write_text(base64.b64encode(key).decode("ascii") + "\n", encoding="utf-8")
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        # Best effort on non-POSIX filesystems.
        pass
    return key


def encrypt_secret(contract_id: str, plaintext_str: str) -> Dict[str, str]:
    safe_contract_id = _safe_contract_id(contract_id)
    plaintext = plaintext_str if isinstance(plaintext_str, str) else str(plaintext_str)
    key = ensure_contract_key(safe_contract_id)
    nonce = os.urandom(12)
    aad = f"mycite:{safe_contract_id}".encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), aad)
    return {
        "alg": "AESGCM",
        "kid": safe_contract_id,
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
    }


def decrypt_secret(contract_id: str, enc_obj: Dict[str, str]) -> str:
    safe_contract_id = _safe_contract_id(contract_id)
    if not isinstance(enc_obj, dict):
        raise ValueError("enc_obj must be a dictionary")

    if str(enc_obj.get("alg") or "") != "AESGCM":
        raise ValueError("Unsupported encryption algorithm")

    nonce_b64 = str(enc_obj.get("nonce_b64") or "").strip()
    ciphertext_b64 = str(enc_obj.get("ciphertext_b64") or "").strip()
    if not nonce_b64 or not ciphertext_b64:
        raise ValueError("Malformed encrypted secret payload")

    nonce = base64.b64decode(nonce_b64)
    ciphertext = base64.b64decode(ciphertext_b64)
    if len(nonce) != 12:
        raise ValueError("AESGCM nonce must be 12 bytes")

    key = ensure_contract_key(safe_contract_id)
    aad = f"mycite:{safe_contract_id}".encode("utf-8")
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad)
    return plaintext.decode("utf-8")


def scrub(value: Any) -> str:
    _ = value
    return "***"

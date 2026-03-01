from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Any


class SignatureVerificationError(ValueError):
    pass


def _as_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    raise SignatureVerificationError("Expected bytes or utf-8 string")


def _sha256_hex(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def canonicalize_request(request) -> bytes:
    """Build canonical bytes for request signature verification.

    Canonical fields:
    - method
    - path
    - raw query string
    - sha256(body)
    - X-MyCite-Timestamp
    - X-MyCite-Nonce
    - Host
    """
    body = request.get_data(cache=True) or b""
    timestamp = (request.headers.get("X-MyCite-Timestamp") or "").strip()
    nonce = (request.headers.get("X-MyCite-Nonce") or "").strip()
    host = (request.headers.get("Host") or "").strip().lower()

    if not timestamp or not nonce:
        raise SignatureVerificationError("Missing required signature headers")

    raw_query = (request.query_string or b"").decode("utf-8", errors="replace")
    parts = [
        request.method.upper(),
        request.path,
        raw_query,
        _sha256_hex(body),
        timestamp,
        nonce,
        host,
    ]
    return "\n".join(parts).encode("utf-8")


def verify_signed_request(request, sender_public_key: str) -> bool:
    """Verify asymmetric signed request.

    Phase 1: default deny unless MYCITE_ALLOW_INSECURE_SIGNATURES=1.
    Phase 2: replace debug branch with Ed25519 verification.
    """
    _ = sender_public_key
    signature = (request.headers.get("X-MyCite-Signature") or "").strip()
    if not signature:
        return False

    try:
        canonicalize_request(request)
    except SignatureVerificationError:
        return False

    return os.environ.get("MYCITE_ALLOW_INSECURE_SIGNATURES", "0") == "1"


def verify_hmac_request(request, shared_secret: str) -> bool:
    """Verify HMAC signature for contract-authenticated calls.

    Expects X-MyCite-Signature to be base64-encoded HMAC-SHA256 over canonical bytes.
    """
    signature_b64 = (request.headers.get("X-MyCite-Signature") or "").strip()
    if not signature_b64:
        return False

    try:
        canonical = canonicalize_request(request)
    except SignatureVerificationError:
        return False

    mac = hmac.new(_as_bytes(shared_secret), canonical, hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode("ascii")
    return hmac.compare_digest(signature_b64, expected)

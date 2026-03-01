from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from flask import abort, jsonify, request

from portal.services.contact_cache import resolve
from portal.services.crypto_signatures import verify_signed_request
from portal.services.request_log_store import append_event


FORBIDDEN_SECRET_KEYS = {
    "private_key", "private_key_pem", "secret", "token", "password",
    "symmetric_key", "hmac_key", "hmac_key_b64", "api_key",
}
EVENT_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON in {path}")
    return payload


def _find_local_public_card(public_dir: Path, sender_msn_id: str) -> Optional[Path]:
    candidates = [
        public_dir / f"{sender_msn_id}.json",
        public_dir / f"msn-{sender_msn_id}.json",
        public_dir / f"mss-{sender_msn_id}.json",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


def _fetch_sender_contact_card(public_dir: Path, sender_msn_id: str) -> Dict[str, Any]:
    local = _find_local_public_card(public_dir, sender_msn_id)
    if local is not None:
        return _read_json(local)

    # Optional remote fallback for multi-node local testing.
    base = os.environ.get("MYCITE_CONTACT_BASE_URL", "").rstrip("/")
    if not base:
        raise FileNotFoundError(f"Sender contact card not found: {sender_msn_id}")

    url = f"{base}/{sender_msn_id}.json"
    with urllib.request.urlopen(url, timeout=3.0) as resp:
        body = resp.read()
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Sender contact card response was not a JSON object")
    return payload


def _reject_forbidden_secret_keys(body: Dict[str, Any]) -> None:
    bad = set(body.keys()).intersection(FORBIDDEN_SECRET_KEYS)
    if bad:
        abort(400, description=f"Body contains forbidden secret keys: {sorted(bad)}")


def _safe_event_id(candidate: str) -> str:
    if candidate and EVENT_ID_RE.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


def _persist_inbox_payload(data_dir: Path, event_id: str, payload: Dict[str, Any]) -> str:
    queue_dir = data_dir / "queue" / "inbox"
    queue_dir.mkdir(parents=True, exist_ok=True)

    payload_path = queue_dir / f"{event_id}.json"
    payload_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return f"data/queue/inbox/{event_id}.json"


def _sanitize_details(body: Dict[str, Any], key_id: str) -> Dict[str, Any]:
    _reject_forbidden_secret_keys(body)

    return {
        "summary": "external request accepted",
        "payload_keys": sorted(body.keys()),
        "payload_size_bytes": len(json.dumps(body, separators=(",", ":")).encode("utf-8")),
        "key_id": key_id or None,
    }


def register_public_inbox_routes(
    app,
    *,
    private_dir: Path,
    public_dir: Path,
    data_dir: Path,
    resolve_contact_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
):
    @app.post("/api/inbox/<msn_id>")
    def public_inbox_receive(msn_id: str):
        sender_msn_id = (request.headers.get("X-MyCite-From") or "").strip()
        key_id = (request.headers.get("X-MyCite-KeyId") or "").strip()

        if not sender_msn_id:
            abort(400, description="Missing required header: X-MyCite-From")
        if not request.is_json:
            abort(415, description="Expected application/json body")

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400, description="Expected JSON object body")

        fetcher = resolve_contact_fn or (lambda s: _fetch_sender_contact_card(public_dir, s))
        try:
            sender_card = resolve(data_dir, sender_msn_id, fetcher)
        except (FileNotFoundError, urllib.error.URLError, ValueError) as e:
            abort(404, description=f"Unable to resolve sender contact card: {e}")

        sender_public_key = sender_card.get("public_key")
        if not isinstance(sender_public_key, str) or not sender_public_key.strip():
            abort(401, description="Sender public key unavailable")

        if not verify_signed_request(request, sender_public_key):
            abort(401, description="Invalid signature")

        details = _sanitize_details(body, key_id)
        body_type = str(body.get("type") or "").strip()

        if body_type == "contract.offer":
            event_id = _safe_event_id(str(body.get("msg_id") or "").strip())
            payload_ref = _persist_inbox_payload(data_dir, event_id, body)
            event = {
                "type": "contract.offer.received",
                "event_id": event_id,
                "from_msn_id": sender_msn_id,
                "auth": "signed",
                "status": "pending",
                "payload_ref": payload_ref,
                "details": details,
            }
            append_event(private_dir, msn_id, event)
            return jsonify(
                {
                    "ok": True,
                    "msn_id": msn_id,
                    "status": "accepted",
                    "auth": "signed",
                    "event_id": event_id,
                    "payload_ref": payload_ref,
                }
            ), 202

        event = {
            "type": "request.received",
            "from_msn_id": sender_msn_id,
            "auth": "signed",
            "status": "pending",
            "details": details,
        }
        append_event(private_dir, msn_id, event)
        return jsonify({"ok": True, "msn_id": msn_id, "status": "accepted", "auth": "signed"}), 202

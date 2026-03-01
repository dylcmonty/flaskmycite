from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from portal.services.request_log_store import append_event


def _read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON in {path}")
    return payload


def _find_local_public_card(public_dir: Path, msn_id: str) -> Optional[Path]:
    candidates = [
        public_dir / f"{msn_id}.json",
        public_dir / f"msn-{msn_id}.json",
        public_dir / f"mss-{msn_id}.json",
    ]
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def fetch_contact_card(
    msn_id: str,
    *,
    base_url: Optional[str] = None,
    public_dir: Optional[Path] = None,
    timeout_seconds: float = 3.0,
) -> Dict[str, Any]:
    target_base = (base_url or os.environ.get("MYCITE_CONTACT_BASE_URL", "")).rstrip("/")
    if target_base:
        url = f"{target_base}/{msn_id}.json"
        req = urllib.request.Request(url=url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read()
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Contact card response was not a JSON object")
        return payload

    local_public_dir = public_dir or (Path(__file__).resolve().parents[2] / "public")
    local_path = _find_local_public_card(local_public_dir, msn_id)
    if local_path is None:
        raise FileNotFoundError(f"Contact card not found for msn_id={msn_id}")
    return _read_json(local_path)


def post_signed_inbox(
    target_base_url: str,
    target_msn_id: str,
    sender_msn_id: str,
    body: Dict[str, Any],
    *,
    key_id: str = "",
    timeout_seconds: float = 5.0,
) -> Tuple[int, Dict[str, Any]]:
    base = target_base_url.rstrip("/")
    if not base:
        raise ValueError("target_base_url is required")
    if not target_msn_id.strip():
        raise ValueError("target_msn_id is required")
    if not sender_msn_id.strip():
        raise ValueError("sender_msn_id is required")

    timestamp = str(int(time.time()))
    nonce = os.environ.get("MYCITE_DEV_NONCE", "dev")
    signature = os.environ.get("MYCITE_DEV_SIGNATURE", "dev")

    payload_bytes = json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-MyCite-From": sender_msn_id,
        "X-MyCite-Timestamp": timestamp,
        "X-MyCite-Nonce": nonce,
        "X-MyCite-Signature": signature,
    }
    if key_id.strip():
        headers["X-MyCite-KeyId"] = key_id.strip()

    url = f"{base}/api/inbox/{target_msn_id}"
    request_obj = urllib.request.Request(url=url, data=payload_bytes, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request_obj, timeout=timeout_seconds) as resp:
            raw = resp.read()
            status_code = int(resp.getcode() or 0)
    except urllib.error.HTTPError as err:
        raw = err.read()
        status_code = int(err.code or 0)
    except urllib.error.URLError as err:
        return 0, {"ok": False, "error": str(err)}

    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
        if not isinstance(parsed, dict):
            parsed = {"raw": parsed}
    except Exception:
        parsed = {"raw": raw.decode("utf-8", errors="replace")}

    return status_code, parsed


def append_outbound_event(
    private_dir: Path,
    msn_id: str,
    *,
    to_msn_id: str,
    event_type: str = "request.sent",
    status: str = "attempted",
    details: Optional[Dict[str, Any]] = None,
) -> Path:
    event = {
        "type": event_type,
        "to_msn_id": to_msn_id,
        "status": status,
        "details": details or {},
    }
    return append_event(private_dir, msn_id, event)

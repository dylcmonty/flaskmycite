from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict

from portal.services.tenant_secrets import encrypt_secret


def _private_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "private"


def _tenant_dir() -> Path:
    return _private_dir() / "progeny" / "tenant"


def _safe_path_token(value: str, *, field: str) -> str:
    token = (value or "").strip()
    if not token:
        raise ValueError(f"{field} is required")
    if "/" in token or "\\" in token or ".." in token:
        raise ValueError(f"{field} must be a stable identifier")
    return token


def _read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON in {path}")
    return payload


def _provider_msn_id() -> str:
    env_msn = str(os.environ.get("MSN_ID") or "").strip()
    if env_msn:
        return env_msn

    for cfg in sorted(_private_dir().glob("mycite-config-*.json")):
        try:
            payload = _read_json(cfg)
        except Exception:
            continue
        msn_id = str(payload.get("msn_id") or "").strip()
        if msn_id:
            return msn_id

    return ""


def _default_profile(tenant_msn_id: str, contract_id: str) -> Dict[str, Any]:
    return {
        "schema": "mycite.progeny.tenant.v1",
        "progeny_type": "tenant",
        "tenant_msn_id": tenant_msn_id,
        "provider_msn_id": _provider_msn_id(),
        "contract_id": contract_id,
        "status": {
            "paypal_configured": False,
            "last_updated_unix_ms": 0,
            "last_error": "",
        },
        "paypal": {
            "client_id": "",
            "client_secret_enc": {
                "alg": "AESGCM",
                "kid": contract_id,
                "nonce_b64": "",
                "ciphertext_b64": "",
            },
            "webhook": {
                "target_url": "",
                "event_mask": ["PAYMENT.CAPTURE.COMPLETED"],
            },
        },
    }


def profile_path(tenant_msn_id: str, contract_id: str) -> Path:
    safe_tenant = _safe_path_token(tenant_msn_id, field="tenant_msn_id")
    safe_contract = _safe_path_token(contract_id, field="contract_id")
    return _tenant_dir() / f"tenant-{safe_tenant}-under-{safe_contract}.json"


def load_profile(tenant_msn_id: str, contract_id: str) -> Dict[str, Any]:
    target = profile_path(tenant_msn_id, contract_id)
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists() and target.is_file():
        payload = _read_json(target)
        payload.setdefault("schema", "mycite.progeny.tenant.v1")
        payload.setdefault("progeny_type", "tenant")
        payload.setdefault("tenant_msn_id", tenant_msn_id)
        payload.setdefault("provider_msn_id", _provider_msn_id())
        payload.setdefault("contract_id", contract_id)
        payload.setdefault("status", {})
        payload.setdefault("paypal", {})
        return payload

    payload = _default_profile(tenant_msn_id, contract_id)
    save_profile(payload)
    return payload


def save_profile(profile_dict: Dict[str, Any]) -> None:
    tenant_msn_id = _safe_path_token(str(profile_dict.get("tenant_msn_id") or ""), field="tenant_msn_id")
    contract_id = _safe_path_token(str(profile_dict.get("contract_id") or ""), field="contract_id")
    target = profile_path(tenant_msn_id, contract_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(profile_dict, indent=2) + "\n", encoding="utf-8")


def _normalize_event_mask(values: list[str]) -> list[str]:
    out: list[str] = []
    seen = set()
    for raw in values:
        token = str(raw or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out or ["PAYMENT.CAPTURE.COMPLETED"]


def set_paypal_config(
    profile: Dict[str, Any],
    client_id: str,
    client_secret_plain: str,
    target_url: str,
    event_mask: list[str],
) -> Dict[str, Any]:
    if not isinstance(profile, dict):
        raise ValueError("profile must be a dictionary")

    contract_id = _safe_path_token(str(profile.get("contract_id") or ""), field="contract_id")
    status = profile.setdefault("status", {})
    if not isinstance(status, dict):
        status = {}
        profile["status"] = status

    paypal = profile.setdefault("paypal", {})
    if not isinstance(paypal, dict):
        paypal = {}
        profile["paypal"] = paypal

    webhook = paypal.setdefault("webhook", {})
    if not isinstance(webhook, dict):
        webhook = {}
        paypal["webhook"] = webhook

    client_secret_enc = paypal.get("client_secret_enc")
    if not isinstance(client_secret_enc, dict):
        client_secret_enc = {
            "alg": "AESGCM",
            "kid": contract_id,
            "nonce_b64": "",
            "ciphertext_b64": "",
        }

    if client_secret_plain:
        client_secret_enc = encrypt_secret(contract_id, client_secret_plain)

    paypal["client_id"] = (client_id or "").strip()
    paypal["client_secret_enc"] = client_secret_enc
    webhook["target_url"] = (target_url or "").strip()
    webhook["event_mask"] = _normalize_event_mask(event_mask)

    has_enc = bool(client_secret_enc.get("ciphertext_b64") and client_secret_enc.get("nonce_b64"))
    is_configured = bool(paypal.get("client_id") and has_enc)

    status["paypal_configured"] = is_configured
    status["last_updated_unix_ms"] = int(time.time() * 1000)
    status["last_error"] = "" if is_configured else "PayPal configuration requires client_id and encrypted secret"

    return profile

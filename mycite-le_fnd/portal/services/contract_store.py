from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


FORBIDDEN_SECRET_KEYS = {
    "private_key", "private_key_pem", "secret", "token", "password",
    "symmetric_key", "hmac_key", "hmac_key_b64", "api_key",
}

ALLOWED_STATUS = {"pending", "active", "revoked", "expired"}


class ContractValidationError(ValueError):
    pass


class ContractNotFoundError(FileNotFoundError):
    pass


class ContractAlreadyExistsError(FileExistsError):
    pass


def _contracts_dir(private_dir: Path) -> Path:
    return private_dir / "contracts"


def _safe_contract_id(contract_id: str) -> str:
    return contract_id.replace("/", "_").replace("..", "_")


def _contract_path(private_dir: Path, contract_id: str) -> Path:
    return _contracts_dir(private_dir) / f"contract-{_safe_contract_id(contract_id)}.json"


def _read_json(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ContractValidationError(f"Invalid contract payload type at {path}")
    return data


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _new_contract_id() -> str:
    return uuid.uuid4().hex


def _reject_secrets(obj: Dict[str, Any]) -> None:
    bad = set(obj.keys()).intersection(FORBIDDEN_SECRET_KEYS)
    if bad:
        raise ContractValidationError(
            f"Do not store secrets in contract metadata. Forbidden keys: {sorted(bad)}"
        )


def _validate_status(data: Dict[str, Any]) -> None:
    status = data.get("status")
    if status is None:
        return
    if status not in ALLOWED_STATUS:
        raise ContractValidationError(f"Invalid contract status: {status}")


def _normalize_for_create(metadata: Dict[str, Any]) -> Dict[str, Any]:
    _reject_secrets(metadata)
    _validate_status(metadata)
    if not str(metadata.get("contract_type", "")).strip():
        raise ContractValidationError("Missing required field: contract_type")
    if not str(metadata.get("counterparty_msn_id", "")).strip():
        raise ContractValidationError("Missing required field: counterparty_msn_id")

    now = int(time.time() * 1000)
    out = dict(metadata)
    out.setdefault("status", "pending")
    out.setdefault("created_unix_ms", now)
    out["updated_unix_ms"] = now
    return out


def _normalize_for_update(existing: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    _reject_secrets(patch)

    out = dict(existing)
    for key, value in patch.items():
        if key in {"contract_id", "created_unix_ms"}:
            continue
        out[key] = value

    _validate_status(out)
    out["updated_unix_ms"] = int(time.time() * 1000)
    return out


def list_contracts(private_dir: Path, filter_type: Optional[str] = None) -> List[Dict[str, Any]]:
    d = _contracts_dir(private_dir)
    if not d.exists():
        return []

    items: List[Dict[str, Any]] = []
    for p in sorted(d.glob("contract-*.json")):
        try:
            data = _read_json(p)
        except Exception:
            continue

        if filter_type and data.get("contract_type") != filter_type:
            continue

        items.append({
            "contract_id": p.stem.replace("contract-", "", 1),
            "contract_type": data.get("contract_type"),
            "counterparty_msn_id": data.get("counterparty_msn_id"),
            "status": data.get("status"),
            "updated_unix_ms": data.get("updated_unix_ms"),
            "path": str(p),
        })
    return items


def get_contract(private_dir: Path, contract_id: str) -> Dict[str, Any]:
    p = _contract_path(private_dir, contract_id)
    if not p.exists():
        raise ContractNotFoundError(f"Contract not found: {contract_id}")
    return _read_json(p)


def create_contract(private_dir: Path, metadata: Dict[str, Any]) -> str:
    contract_id = (metadata.get("contract_id") or "").strip() or _new_contract_id()
    p = _contract_path(private_dir, contract_id)
    if p.exists():
        raise ContractAlreadyExistsError(f"Contract already exists: {contract_id}")

    payload = dict(metadata)
    payload.pop("contract_id", None)
    normalized = _normalize_for_create(payload)
    _write_json(p, normalized)
    return contract_id


def update_contract(private_dir: Path, contract_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    p = _contract_path(private_dir, contract_id)
    if not p.exists():
        raise ContractNotFoundError(f"Contract not found: {contract_id}")

    existing = _read_json(p)
    normalized = _normalize_for_update(existing, patch)
    _write_json(p, normalized)
    return normalized

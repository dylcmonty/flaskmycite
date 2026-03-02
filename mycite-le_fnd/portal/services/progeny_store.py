from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def _tenant_dir(private_dir: Path) -> Path:
    return private_dir / "progeny" / "tenant"


def _read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON in {path}")
    return payload


def _safe_lookup_id(value: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return ""
    if "/" in normalized or "\\" in normalized or ".." in normalized:
        return ""
    return normalized


def _match_tenant(payload: Dict[str, Any], tenant_id: str) -> bool:
    candidates = [
        str(payload.get("child_msn_id") or "").strip(),
        str(payload.get("tenant_id") or "").strip(),
        str(payload.get("msn_id") or "").strip(),
    ]
    return tenant_id in {c for c in candidates if c}


def load_tenant_progeny(private_dir: Path, alias_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    _ = _safe_lookup_id(alias_id)
    safe_tenant_id = _safe_lookup_id(tenant_id)
    if not safe_tenant_id:
        return None

    tenant_path = _tenant_dir(private_dir)
    if not tenant_path.exists() or not tenant_path.is_dir():
        return None

    for candidate in sorted(tenant_path.glob("*.json")):
        if not candidate.is_file():
            continue
        try:
            payload = _read_json(candidate)
        except Exception:
            continue

        if _match_tenant(payload, safe_tenant_id):
            return payload

    return None

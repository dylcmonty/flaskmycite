from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

CLIENT_KEY_BY_MSN = {
    "3-2-3-17-77-2-6-1-1-2": "cvcc",
    "3-2-3-17-77-2-6-3-1-6": "tff",
}


def _aliases_dir(private_dir: Path) -> Path:
    return private_dir / "aliases"


def _safe_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_-]+", "-", (value or "").strip())
    token = token.strip("-")
    return token or "unknown"


def alias_filename(client_msn_id: str, company_msn_id: str, progeny_type: str) -> str:
    return (
        f"alias-{_safe_token(client_msn_id)}-"
        f"{_safe_token(company_msn_id)}-"
        f"{_safe_token(progeny_type)}"
    )


def alias_path(private_dir: Path, alias_id: str) -> Path:
    if not alias_id or "/" in alias_id or "\\" in alias_id or ".." in alias_id:
        raise ValueError("alias_id must be a stable identifier")
    return _aliases_dir(private_dir) / f"{alias_id}.json"


def client_key_for_msn(client_msn_id: str) -> Optional[str]:
    key = CLIENT_KEY_BY_MSN.get((client_msn_id or "").strip())
    if key:
        return key
    return None


def merge_field_names(*field_lists: Iterable[str]) -> list[str]:
    seen = set()
    out: list[str] = []
    for values in field_lists:
        for raw in values:
            key = str(raw or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(key)
    return out


def build_alias_from_contract(
    *,
    company_msn_id: str,
    client_msn_id: str,
    contract_id: str,
    progeny_type: str,
    field_names: Iterable[str],
    host_title: str = "",
    alias_msn_id: str = "",
    child_msn_id: str = "",
    status: str = "active",
) -> Dict[str, Any]:
    fields = {name: "" for name in merge_field_names(field_names)}
    payload: Dict[str, Any] = {
        "msn_id": alias_msn_id or company_msn_id,
        "alias_host": client_msn_id,
        "host_title": host_title or f"client_{client_msn_id}",
        "company_msn_id": company_msn_id,
        "client_msn_id": client_msn_id,
        "contract_id": contract_id,
        "progeny_type": progeny_type,
        "status": status,
        "fields": fields,
    }
    if child_msn_id:
        payload["child_msn_id"] = child_msn_id
    return payload


def write_alias_file(private_dir: Path, alias_id: str, payload: Dict[str, Any]) -> Path:
    target = alias_path(private_dir, alias_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target

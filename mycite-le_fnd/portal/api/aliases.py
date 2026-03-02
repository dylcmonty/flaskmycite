from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from flask import abort, jsonify, make_response, request

from portal.services.progeny_store import load_tenant_progeny


def _aliases_dir(private_dir: Path) -> Path:
    return private_dir / "aliases"


def _read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON in {path}")
    return payload


def _safe_alias_id(alias_id: str) -> str:
    normalized = (alias_id or "").strip()
    if (
        not normalized
        or "/" in normalized
        or "\\" in normalized
        or ".." in normalized
    ):
        raise ValueError("alias_id must be a stable identifier, not a path")
    return normalized


def _enrich_tenant(private_dir: Path, record: Dict[str, Any]) -> Dict[str, Any]:
    progeny_type = str(record.get("progeny_type") or "").strip().lower()
    if progeny_type != "tenant":
        return record

    alias_id = str(record.get("alias_id") or "").strip()
    tenant_id = str(record.get("child_msn_id") or record.get("tenant_id") or "").strip()
    if not alias_id or not tenant_id:
        return record

    tenant = load_tenant_progeny(private_dir, alias_id, tenant_id)
    if tenant is None:
        return record

    out = dict(record)
    out["tenant_progeny"] = tenant
    return out


def list_alias_records(private_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    aliases_path = _aliases_dir(private_dir)
    if not aliases_path.exists() or not aliases_path.is_dir():
        return [], {}

    items: List[Dict[str, Any]] = []
    errors: Dict[str, str] = {}

    for alias_path in sorted(aliases_path.glob("*.json")):
        alias_id = alias_path.stem
        try:
            payload = _read_json(alias_path)
        except Exception as e:
            errors[alias_id] = f"Failed to read alias JSON: {e}"
            continue

        record = dict(payload)
        record.setdefault("alias_id", alias_id)
        items.append(_enrich_tenant(private_dir, record))

    return items, errors


def get_alias_record(private_dir: Path, alias_id: str) -> Dict[str, Any]:
    safe_alias_id = _safe_alias_id(alias_id)
    alias_path = _aliases_dir(private_dir) / f"{safe_alias_id}.json"
    if not alias_path.exists() or not alias_path.is_file():
        raise FileNotFoundError(f"No alias record found for alias_id={safe_alias_id}")

    payload = _read_json(alias_path)
    record = dict(payload)
    record.setdefault("alias_id", safe_alias_id)
    return _enrich_tenant(private_dir, record)


def register_aliases_routes(
    app,
    *,
    private_dir: Path,
    options_private_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
):
    @app.get("/portal/api/aliases")
    def portal_aliases_get():
        msn_id = (request.args.get("msn_id") or "").strip()
        if not msn_id:
            abort(400, description="Missing required query param: msn_id")

        records, errors = list_alias_records(private_dir)
        aliases: Dict[str, Any] = {}

        for record in records:
            alias_id = str(record.get("alias_id") or "").strip()
            if not alias_id:
                continue
            alias_msn_id = str(record.get("msn_id") or "").strip()
            if alias_msn_id and alias_msn_id != msn_id:
                continue
            aliases[alias_id] = record

        out: Dict[str, Any] = {
            "msn_id": msn_id,
            "schema": "mycite.alias.bundle.v0",
            "aliases": aliases,
            "errors": errors,
        }
        if options_private_fn is not None:
            out["options_private"] = options_private_fn(msn_id)
        return jsonify(out)

    @app.route("/portal/api/aliases", methods=["OPTIONS"])
    def portal_aliases_options():
        resp = make_response("", 204)
        resp.headers["Allow"] = "GET, OPTIONS"
        return resp

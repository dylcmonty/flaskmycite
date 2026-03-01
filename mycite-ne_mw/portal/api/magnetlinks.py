from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from flask import abort, jsonify, make_response, request

from portal.services.contract_store import (
    ContractAlreadyExistsError,
    ContractNotFoundError,
    ContractValidationError,
    create_contract,
    list_contracts,
    update_contract,
)


def _as_int(value: Optional[str], default: int, *, min_value: int = 0, max_value: int = 10_000) -> int:
    if value is None or value == "":
        return default
    try:
        n = int(value)
    except Exception:
        return default
    if n < min_value:
        return min_value
    if n > max_value:
        return max_value
    return n


def register_magnetlinks_routes(
    app,
    *,
    private_dir: Path,
    options_private_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
):
    """Register portal-only magnet-link metadata endpoints."""

    @app.get("/portal/api/magnetlinks")
    def magnetlinks_list():
        msn_id = (request.args.get("msn_id") or "").strip()
        if not msn_id:
            abort(400, description="Missing required query param: msn_id")

        limit = _as_int(request.args.get("limit"), 200, min_value=1, max_value=2000)
        offset = _as_int(request.args.get("offset"), 0, min_value=0, max_value=10_000_000)

        items = list_contracts(private_dir, filter_type="magnetlink")
        sliced = items[offset: offset + limit]

        out: Dict[str, Any] = {
            "msn_id": msn_id,
            "magnetlinks": sliced,
            "meta": {"limit": limit, "offset": offset, "returned": len(sliced), "total": len(items)},
        }
        if options_private_fn is not None:
            out["options_private"] = options_private_fn(msn_id)
        return jsonify(out)

    @app.post("/portal/api/magnetlinks")
    def magnetlinks_create():
        msn_id = (request.args.get("msn_id") or "").strip()
        if not msn_id:
            abort(400, description="Missing required query param: msn_id")

        if not request.is_json:
            abort(415, description="Expected application/json body")
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400, description="Expected JSON object body")

        payload = dict(body)
        payload["contract_type"] = "magnetlink"

        try:
            contract_id = create_contract(private_dir, payload)
        except ContractValidationError as e:
            abort(400, description=str(e))
        except ContractAlreadyExistsError as e:
            abort(409, description=str(e))

        return jsonify({"ok": True, "msn_id": msn_id, "contract_id": contract_id})

    @app.post("/portal/api/magnetlinks/check")
    def magnetlinks_check():
        msn_id = (request.args.get("msn_id") or "").strip()
        if not msn_id:
            abort(400, description="Missing required query param: msn_id")

        updated: List[str] = []
        now = int(time.time() * 1000)
        for entry in list_contracts(private_dir, filter_type="magnetlink"):
            contract_id = entry.get("contract_id")
            if not isinstance(contract_id, str) or not contract_id:
                continue
            try:
                update_contract(
                    private_dir,
                    contract_id,
                    {"last_checked_unix_ms": now},
                )
            except (ContractNotFoundError, ContractValidationError):
                continue
            updated.append(contract_id)

        out: Dict[str, Any] = {"ok": True, "msn_id": msn_id, "checked": updated}
        if options_private_fn is not None:
            out["options_private"] = options_private_fn(msn_id)
        return jsonify(out)

    @app.route("/portal/api/magnetlinks", methods=["OPTIONS"])
    def magnetlinks_options():
        resp = make_response("", 204)
        resp.headers["Allow"] = "GET, POST, OPTIONS"
        return resp

    @app.route("/portal/api/magnetlinks/check", methods=["OPTIONS"])
    def magnetlinks_check_options():
        resp = make_response("", 204)
        resp.headers["Allow"] = "POST, OPTIONS"
        return resp

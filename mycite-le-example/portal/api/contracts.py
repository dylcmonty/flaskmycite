from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from flask import abort, jsonify, make_response, request

from portal.services.contract_store import (
    ContractAlreadyExistsError,
    ContractNotFoundError,
    ContractValidationError,
    create_contract,
    get_contract,
    list_contracts,
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


def register_contract_routes(
    app,
    *,
    private_dir: Path,
    options_private_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
):
    """Register portal-only contract metadata endpoints."""

    @app.get("/portal/api/contracts")
    def contracts_list():
        msn_id = (request.args.get("msn_id") or "").strip()
        if not msn_id:
            abort(400, description="Missing required query param: msn_id")

        contract_type = (request.args.get("type") or "").strip() or None
        limit = _as_int(request.args.get("limit"), 200, min_value=1, max_value=2000)
        offset = _as_int(request.args.get("offset"), 0, min_value=0, max_value=10_000_000)

        items = list_contracts(private_dir, filter_type=contract_type)
        sliced = items[offset: offset + limit]
        out: Dict[str, Any] = {
            "msn_id": msn_id,
            "contracts": sliced,
            "meta": {"limit": limit, "offset": offset, "returned": len(sliced), "total": len(items)},
        }
        if options_private_fn is not None:
            out["options_private"] = options_private_fn(msn_id)
        return jsonify(out)

    @app.get("/portal/api/contracts/<contract_id>")
    def contracts_get(contract_id: str):
        msn_id = (request.args.get("msn_id") or "").strip()
        if not msn_id:
            abort(400, description="Missing required query param: msn_id")

        try:
            data = get_contract(private_dir, contract_id)
        except ContractNotFoundError as e:
            abort(404, description=str(e))

        out: Dict[str, Any] = {"msn_id": msn_id, "contract_id": contract_id, "contract": data}
        if options_private_fn is not None:
            out["options_private"] = options_private_fn(msn_id)
        return jsonify(out)

    @app.post("/portal/api/contracts")
    def contracts_create():
        msn_id = (request.args.get("msn_id") or "").strip()
        if not msn_id:
            abort(400, description="Missing required query param: msn_id")

        if not request.is_json:
            abort(415, description="Expected application/json body")
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400, description="Expected JSON object body")

        try:
            contract_id = create_contract(private_dir, body)
        except ContractValidationError as e:
            abort(400, description=str(e))
        except ContractAlreadyExistsError as e:
            abort(409, description=str(e))

        return jsonify({"ok": True, "msn_id": msn_id, "contract_id": contract_id})

    @app.route("/portal/api/contracts", methods=["OPTIONS"])
    def contracts_options():
        resp = make_response("", 204)
        resp.headers["Allow"] = "GET, POST, OPTIONS"
        return resp

    @app.route("/portal/api/contracts/<contract_id>", methods=["OPTIONS"])
    def contracts_get_options(contract_id: str):
        resp = make_response("", 204)
        resp.headers["Allow"] = "GET, OPTIONS"
        return resp

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from flask import abort, jsonify, make_response, request

from portal.services.alias_factory import (
    alias_filename,
    build_alias_from_contract,
    client_key_for_msn,
    merge_field_names,
    write_alias_file,
)
from portal.services.contract_store import (
    ContractAlreadyExistsError,
    ContractNotFoundError,
    ContractValidationError,
    create_contract,
    get_contract,
    list_contracts,
)
from portal.services.progeny_config_store import get_client_config, get_config
from portal.services.request_log_store import append_event


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


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _maybe_create_alias(
    *,
    private_dir: Path,
    local_msn_id: str,
    contract_id: str,
    contract_payload: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    progeny_type = _as_str(contract_payload.get("progeny_type"))
    if not progeny_type:
        return None

    client_msn_id = _as_str(contract_payload.get("client_msn_id")) or _as_str(
        contract_payload.get("counterparty_msn_id")
    )
    if not client_msn_id:
        return None

    base_cfg = get_config(progeny_type)
    base_fields = base_cfg.get("fields") if isinstance(base_cfg.get("fields"), list) else []

    client_overlay_fields = []
    client_key = client_key_for_msn(client_msn_id)
    if client_key:
        client_cfg = get_client_config(client_key)
        if isinstance(client_cfg, dict) and isinstance(client_cfg.get("fields"), list):
            client_overlay_fields = client_cfg.get("fields") or []

    alias_id = alias_filename(client_msn_id, local_msn_id, progeny_type)
    alias_payload = build_alias_from_contract(
        company_msn_id=local_msn_id,
        client_msn_id=client_msn_id,
        contract_id=contract_id,
        progeny_type=progeny_type,
        field_names=merge_field_names(base_fields, client_overlay_fields),
        host_title=_as_str(contract_payload.get("host_title")),
        alias_msn_id=_as_str(contract_payload.get("msn_id")) or local_msn_id,
        child_msn_id=_as_str(contract_payload.get("child_msn_id")),
        status=_as_str(contract_payload.get("status")) or "active",
    )
    alias_path = write_alias_file(private_dir, alias_id, alias_payload)

    append_event(
        private_dir,
        local_msn_id,
        {
            "type": "alias.created",
            "status": "active",
            "alias_id": alias_id,
            "client_msn_id": client_msn_id,
            "company_msn_id": local_msn_id,
            "contract_id": contract_id,
            "progeny_type": progeny_type,
            "details": {"alias_path": str(alias_path)},
        },
    )

    return {"alias_id": alias_id, "alias_path": str(alias_path)}


def register_contract_routes(
    app,
    *,
    private_dir: Path,
    options_private_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
):
    @app.get("/portal/api/contracts")
    def contracts_list():
        msn_id = (request.args.get("msn_id") or "").strip()
        if not msn_id:
            abort(400, description="Missing required query param: msn_id")

        contract_type = (request.args.get("type") or "").strip() or None
        limit = _as_int(request.args.get("limit"), 200, min_value=1, max_value=2000)
        offset = _as_int(request.args.get("offset"), 0, min_value=0, max_value=10_000_000)

        items = list_contracts(private_dir, filter_type=contract_type)
        sliced = items[offset : offset + limit]
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

        alias_info: Optional[Dict[str, Any]] = None
        if _as_str(body.get("progeny_type")):
            try:
                alias_info = _maybe_create_alias(
                    private_dir=private_dir,
                    local_msn_id=msn_id,
                    contract_id=contract_id,
                    contract_payload=body,
                )
            except FileNotFoundError as e:
                abort(400, description=f"Unable to build alias: {e}")
            except ValueError as e:
                abort(400, description=f"Unable to build alias: {e}")

        out: Dict[str, Any] = {"ok": True, "msn_id": msn_id, "contract_id": contract_id}
        if alias_info:
            out["alias"] = alias_info
        return jsonify(out)

    @app.route("/portal/api/contracts", methods=["OPTIONS"])
    def contracts_options():
        resp = make_response("", 204)
        resp.headers["Allow"] = "GET, POST, OPTIONS"
        return resp

    @app.route("/portal/api/contracts/<contract_id>", methods=["OPTIONS"])
    def contracts_get_options(contract_id: str):
        _ = contract_id
        resp = make_response("", 204)
        resp.headers["Allow"] = "GET, OPTIONS"
        return resp

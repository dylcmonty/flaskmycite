from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from flask import abort, jsonify, make_response, request

from portal.services.contract_store import (
    ContractAlreadyExistsError,
    ContractNotFoundError,
    ContractValidationError,
    create_contract,
    get_contract,
    list_contracts,
    update_contract,
)
from portal.services.outbound_requests import post_signed_inbox
from portal.services.request_log_store import append_event

DEFAULT_CLIENT_MSN_IDS = [
    "3-2-3-17-77-2-6-1-1-2",  # CVCC
    "3-2-3-17-77-2-6-3-1-6",  # TFF
]
_ALLOWED_TYPES = {"magnetlink", "paypal_tool"}


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


def _safe_contract_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-") or "paypal"


def _config_path(private_dir: Path, msn_id: str) -> Path:
    return private_dir / f"mycite-config-{msn_id}.json"


def _read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON in {path}")
    return payload


def _counterparty_base_urls(private_dir: Path, msn_id: str) -> Dict[str, str]:
    path = _config_path(private_dir, msn_id)
    if not path.exists() or not path.is_file():
        return {}
    try:
        cfg = _read_json(path)
    except Exception:
        return {}

    policy = cfg.get("contract_policy")
    if not isinstance(policy, dict):
        return {}
    raw = policy.get("counterparty_base_urls")
    if not isinstance(raw, dict):
        return {}

    out: Dict[str, str] = {}
    for key, value in raw.items():
        k = _as_str(key)
        v = _as_str(value)
        if k and v:
            out[k] = v
    return out


def _paypal_contract_id(client_msn_id: str) -> str:
    return f"paypal-demo-{_safe_contract_id(client_msn_id)}"


def _upsert_paypal_contract(private_dir: Path, *, client_msn_id: str, version: str) -> str:
    contract_id = _paypal_contract_id(client_msn_id)
    create_payload = {
        "contract_id": contract_id,
        "contract_type": "paypal_tool",
        "counterparty_msn_id": client_msn_id,
        "tool_name": "paypal_demo",
        "version": version,
        "status": "pending",
    }
    try:
        create_contract(private_dir, create_payload)
    except ContractAlreadyExistsError:
        update_contract(
            private_dir,
            contract_id,
            {
                "tool_name": "paypal_demo",
                "version": version,
                "status": "pending",
            },
        )
    return contract_id


def register_magnetlinks_routes(
    app,
    *,
    private_dir: Path,
    options_private_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
):
    @app.get("/portal/api/magnetlinks")
    def magnetlinks_list():
        msn_id = (request.args.get("msn_id") or "").strip()
        if not msn_id:
            abort(400, description="Missing required query param: msn_id")

        limit = _as_int(request.args.get("limit"), 200, min_value=1, max_value=2000)
        offset = _as_int(request.args.get("offset"), 0, min_value=0, max_value=10_000_000)
        filter_type = _as_str(request.args.get("type"))

        if filter_type and filter_type not in _ALLOWED_TYPES:
            abort(400, description=f"Unsupported type filter: {filter_type}")

        if filter_type:
            items = list_contracts(private_dir, filter_type=filter_type)
        else:
            items = [
                item
                for item in list_contracts(private_dir)
                if _as_str(item.get("contract_type")) in _ALLOWED_TYPES
            ]

        sliced = items[offset : offset + limit]

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
        contract_type = _as_str(payload.get("contract_type")) or "magnetlink"
        if contract_type not in _ALLOWED_TYPES:
            abort(400, description=f"Unsupported contract_type: {contract_type}")
        payload["contract_type"] = contract_type

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
        filter_type = _as_str(request.args.get("type"))

        entries = list_contracts(private_dir, filter_type=filter_type or None)
        for entry in entries:
            if _as_str(entry.get("contract_type")) not in _ALLOWED_TYPES:
                continue
            contract_id = entry.get("contract_id")
            if not isinstance(contract_id, str) or not contract_id:
                continue
            try:
                update_contract(private_dir, contract_id, {"last_checked_unix_ms": now})
            except (ContractNotFoundError, ContractValidationError):
                continue
            updated.append(contract_id)

        out: Dict[str, Any] = {"ok": True, "msn_id": msn_id, "checked": updated}
        if options_private_fn is not None:
            out["options_private"] = options_private_fn(msn_id)
        return jsonify(out)

    @app.post("/portal/api/tools/paypal_demo/update")
    def paypal_demo_update():
        msn_id = (request.args.get("msn_id") or "").strip()
        if not msn_id:
            abort(400, description="Missing required query param: msn_id")

        if not request.is_json:
            abort(415, description="Expected application/json body")
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400, description="Expected JSON object body")

        version = _as_str(body.get("version"))
        if not version:
            abort(400, description="version is required")

        client_msn_ids = body.get("client_msn_ids")
        if not isinstance(client_msn_ids, list) or not client_msn_ids:
            client_msn_ids = list(DEFAULT_CLIENT_MSN_IDS)

        counterparty_urls = _counterparty_base_urls(private_dir, msn_id)
        results: List[Dict[str, Any]] = []
        for raw_client_id in client_msn_ids:
            client_msn_id = _as_str(raw_client_id)
            if not client_msn_id:
                continue

            contract_id = _upsert_paypal_contract(
                private_dir,
                client_msn_id=client_msn_id,
                version=version,
            )

            target_base_url = _as_str(counterparty_urls.get(client_msn_id))
            status_code = 0
            response_payload: Dict[str, Any] = {"ok": False, "reason": "no_target_base_url"}
            if target_base_url:
                status_code, response_payload = post_signed_inbox(
                    target_base_url=target_base_url,
                    target_msn_id=client_msn_id,
                    sender_msn_id=msn_id,
                    body={
                        "schema": "mycite.message.v0",
                        "type": "tool.update.offer",
                        "msg_id": f"paypal-demo-{client_msn_id}-{int(time.time())}",
                        "contract": {
                            "contract_id": contract_id,
                            "contract_type": "paypal_tool",
                            "initiator_msn_id": msn_id,
                            "counterparty_msn_id": client_msn_id,
                            "tool_name": "paypal_demo",
                            "version": version,
                        },
                    },
                )

            append_event(
                private_dir,
                msn_id,
                {
                    "type": "tool.update.sent",
                    "to_msn_id": client_msn_id,
                    "contract_id": contract_id,
                    "status": "sent" if status_code else "stubbed",
                    "details": {
                        "tool_name": "paypal_demo",
                        "version": version,
                        "outbound_status_code": status_code,
                        "outbound_response": response_payload,
                    },
                },
            )

            results.append(
                {
                    "client_msn_id": client_msn_id,
                    "contract_id": contract_id,
                    "status_code": status_code,
                    "response": response_payload,
                }
            )

        return jsonify({"ok": True, "msn_id": msn_id, "version": version, "results": results})

    @app.post("/portal/api/tools/paypal_demo/confirm")
    def paypal_demo_confirm():
        msn_id = (request.args.get("msn_id") or "").strip()
        if not msn_id:
            abort(400, description="Missing required query param: msn_id")

        if not request.is_json:
            abort(415, description="Expected application/json body")
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400, description="Expected JSON object body")

        client_msn_id = _as_str(body.get("client_msn_id"))
        if not client_msn_id:
            abort(400, description="client_msn_id is required")

        contract_id = _as_str(body.get("contract_id")) or _paypal_contract_id(client_msn_id)
        version = _as_str(body.get("version"))
        status = _as_str(body.get("status")) or "confirmed"

        try:
            existing = get_contract(private_dir, contract_id)
        except ContractNotFoundError as e:
            abort(404, description=str(e))

        confirmations = existing.get("confirmations")
        if not isinstance(confirmations, dict):
            confirmations = {}

        confirmations[client_msn_id] = {
            "version": version,
            "status": status,
            "confirmed_unix_ms": int(time.time() * 1000),
        }

        try:
            update_contract(
                private_dir,
                contract_id,
                {
                    "confirmations": confirmations,
                    "status": "active",
                },
            )
        except (ContractValidationError, ContractNotFoundError) as e:
            abort(400, description=str(e))

        append_event(
            private_dir,
            msn_id,
            {
                "type": "tool.update.confirmed",
                "from_msn_id": client_msn_id,
                "contract_id": contract_id,
                "status": "confirmed",
                "details": {
                    "tool_name": "paypal_demo",
                    "version": version,
                },
            },
        )

        return jsonify({"ok": True, "msn_id": msn_id, "client_msn_id": client_msn_id, "contract_id": contract_id})

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

    @app.route("/portal/api/tools/paypal_demo/update", methods=["OPTIONS"])
    def paypal_demo_update_options():
        resp = make_response("", 204)
        resp.headers["Allow"] = "POST, OPTIONS"
        return resp

    @app.route("/portal/api/tools/paypal_demo/confirm", methods=["OPTIONS"])
    def paypal_demo_confirm_options():
        resp = make_response("", 204)
        resp.headers["Allow"] = "POST, OPTIONS"
        return resp

from __future__ import annotations

from typing import Any, Callable, Optional

from flask import abort, jsonify, redirect, request


def register_data_routes(
    app,
    *,
    workspace,
    aliases_provider: Callable[[], list[dict]] | None = None,
    options_private_fn: Optional[Callable[[str], dict[str, Any]]] = None,
    msn_id_provider: Optional[Callable[[], str]] = None,
    include_home_redirect: bool = True,
    include_legacy_shims: bool = True,
) -> None:
    def _known_table_ids() -> set[str]:
        return {
            str(item.get("table_id") or "").strip()
            for item in workspace.list_tables()
            if str(item.get("table_id") or "").strip()
        }

    def _msn_id() -> str:
        if msn_id_provider is None:
            return ""
        try:
            return str(msn_id_provider() or "").strip()
        except Exception:
            return ""

    def _json_body() -> dict[str, Any]:
        if not request.is_json:
            abort(415, description="Expected application/json body")
        payload = request.get_json(silent=True)
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str):
            return {"directive": payload}
        abort(400, description="Expected JSON object body")

    def _state_snapshot() -> dict[str, Any]:
        return workspace.get_state_snapshot()

    def _state_payload(result: dict[str, Any]) -> dict[str, Any]:
        snapshot = _state_snapshot()
        return {
            "ok": bool(result.get("ok", True)),
            "result": result,
            "state": snapshot.get("state", {}),
            "left_pane_vm": snapshot.get("left_pane_vm", {}),
            "right_pane_vm": snapshot.get("right_pane_vm", {}),
            "staged_edits": snapshot.get("staged_edits", []),
            "errors": list(result.get("errors") or []),
            "warnings": list(result.get("warnings") or []),
        }

    if include_home_redirect:
        @app.get("/portal/data")
        def portal_data_home_redirect():
            return redirect("/portal/tools/data_tool/home", code=302)

    @app.get("/portal/api/data/state")
    def portal_data_state():
        snapshot = _state_snapshot()
        snapshot["ok"] = True
        msn_id = _msn_id()
        if options_private_fn is not None and msn_id:
            snapshot["options_private"] = options_private_fn(msn_id)
        return jsonify(snapshot)

    @app.post("/portal/api/data/directive")
    def portal_data_directive():
        body = _json_body()
        result = workspace.apply_directive(body)
        result["ok"] = not bool(result.get("errors"))
        return jsonify(result)

    @app.post("/portal/api/data/stage_edit")
    def portal_data_stage_edit():
        body = _json_body()
        result = workspace.stage_edit(
            row_id=str(body.get("row_id") or "").strip(),
            field_id=str(body.get("field_id") or "").strip(),
            display_value=str(body.get("display_value") or ""),
            table_id=str(body.get("table_id") or "").strip() or None,
            instance_id=str(body.get("instance_id") or "").strip() or None,
        )
        return jsonify(_state_payload(result))

    @app.post("/portal/api/data/reset_staging")
    def portal_data_reset_staging():
        body = _json_body()
        result = workspace.reset_staging(
            scope=str(body.get("scope") or "all").strip().lower(),
            table_id=str(body.get("table_id") or "").strip() or None,
            row_id=str(body.get("row_id") or "").strip() or None,
        )
        return jsonify(_state_payload(result))

    @app.post("/portal/api/data/commit")
    def portal_data_commit():
        body = _json_body()
        result = workspace.commit(
            scope=str(body.get("scope") or "all").strip().lower(),
            table_id=str(body.get("table_id") or "").strip() or None,
            row_id=str(body.get("row_id") or "").strip() or None,
        )
        return jsonify(_state_payload(result))

    if not include_legacy_shims:
        return

    @app.get("/portal/api/data/tables")
    def portal_data_tables():
        data: dict[str, Any] = {
            "ok": True,
            "tables": workspace.list_tables(),
            "warnings": ["deprecated endpoint: use /portal/api/data/state and /portal/api/data/directive"],
        }
        msn_id = _msn_id()
        if options_private_fn is not None and msn_id:
            data["options_private"] = options_private_fn(msn_id)
        return jsonify(data)

    @app.get("/portal/api/data/table/<table_id>/instances")
    def portal_data_instances(table_id: str):
        if table_id not in _known_table_ids():
            abort(404, description=f"Unknown table_id: {table_id}")
        return jsonify(
            {
                "ok": True,
                "table_id": table_id,
                "instances": workspace.list_instances(table_id),
                "warnings": ["deprecated endpoint"],
            }
        )

    @app.get("/portal/api/data/table/<table_id>/view")
    def portal_data_view(table_id: str):
        if table_id not in _known_table_ids():
            abort(404, description=f"Unknown table_id: {table_id}")
        instance_id = (request.args.get("instance") or "").strip() or None
        mode = (request.args.get("mode") or "general").strip().lower()
        view = workspace.get_view(table_id, instance_id=instance_id, mode=mode)
        return jsonify({"ok": True, "view": view, "warnings": ["deprecated endpoint"]})

    @app.post("/portal/api/data/revert_edit")
    def portal_data_revert_edit():
        body = _json_body()
        result = workspace.revert_edit(
            table_id=str(body.get("table_id") or "").strip(),
            row_id=str(body.get("row_id") or "").strip(),
            field_id=str(body.get("field_id") or "").strip(),
        )
        payload = _state_payload(result)
        payload.setdefault("warnings", []).append("deprecated endpoint")
        return jsonify(payload)

    @app.post("/portal/api/data/reset")
    def portal_data_reset():
        body = _json_body()
        scope = str(body.get("scope") or "all").strip().lower()
        table_id = str(body.get("table_id") or "").strip() or None
        result = workspace.reset_staging(scope=scope, table_id=table_id)
        payload = _state_payload(result)
        payload.setdefault("warnings", []).append("deprecated endpoint")
        return jsonify(payload)

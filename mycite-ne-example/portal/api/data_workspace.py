from __future__ import annotations

from typing import Any, Callable, Optional

from flask import abort, jsonify, render_template, request


def register_data_routes(
    app,
    *,
    workspace,
    aliases_provider: Callable[[], list[dict]],
    options_private_fn: Optional[Callable[[str], dict[str, Any]]] = None,
    msn_id_provider: Optional[Callable[[], str]] = None,
) -> None:
    def _known_table_ids() -> set[str]:
        out = set()
        for item in workspace.list_tables():
            token = str(item.get("table_id") or "").strip()
            if token:
                out.add(token)
        return out

    def _aliases() -> list[dict]:
        try:
            return list(aliases_provider() or [])
        except Exception:
            return []

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
        if not isinstance(payload, dict):
            abort(400, description="Expected JSON object body")
        return payload

    @app.get("/portal/data")
    def portal_data_home():
        return render_template(
            "data/data_home.html",
            aliases=_aliases(),
            msn_id=_msn_id(),
            default_mode="general",
        )

    @app.get("/portal/api/data/tables")
    def portal_data_tables():
        data: dict[str, Any] = {"ok": True, "tables": workspace.list_tables()}
        msn_id = _msn_id()
        if options_private_fn is not None and msn_id:
            data["options_private"] = options_private_fn(msn_id)
        return jsonify(data)

    @app.get("/portal/api/data/table/<table_id>/instances")
    def portal_data_instances(table_id: str):
        if table_id not in _known_table_ids():
            abort(404, description=f"Unknown table_id: {table_id}")
        return jsonify({"ok": True, "table_id": table_id, "instances": workspace.list_instances(table_id)})

    @app.get("/portal/api/data/table/<table_id>/view")
    def portal_data_view(table_id: str):
        if table_id not in _known_table_ids():
            abort(404, description=f"Unknown table_id: {table_id}")
        instance_id = (request.args.get("instance") or "").strip() or None
        mode = (request.args.get("mode") or "general").strip().lower()
        if mode not in {"general", "inspect"}:
            abort(400, description="mode must be one of: general, inspect")
        view = workspace.get_view(table_id, instance_id=instance_id, mode=mode)
        return jsonify({"ok": True, "view": view})

    @app.post("/portal/api/data/stage_edit")
    def portal_data_stage_edit():
        body = _json_body()
        table_id = str(body.get("table_id") or "").strip()
        row_id = str(body.get("row_id") or "").strip()
        field_id = str(body.get("field_id") or "").strip()
        display_value = str(body.get("display_value") or "")
        mode = str(body.get("mode") or "general").strip().lower()
        instance_id = str(body.get("instance_id") or "").strip() or None

        result = workspace.stage_edit(table_id, row_id, field_id, display_value)
        view = workspace.get_view(table_id, instance_id=instance_id, mode=mode) if table_id else None
        return jsonify({"ok": bool(result.get("ok")), "result": result, "view": view})

    @app.post("/portal/api/data/revert_edit")
    def portal_data_revert_edit():
        body = _json_body()
        table_id = str(body.get("table_id") or "").strip()
        row_id = str(body.get("row_id") or "").strip()
        field_id = str(body.get("field_id") or "").strip()
        mode = str(body.get("mode") or "general").strip().lower()
        instance_id = str(body.get("instance_id") or "").strip() or None

        result = workspace.revert_edit(table_id, row_id, field_id)
        view = workspace.get_view(table_id, instance_id=instance_id, mode=mode) if table_id else None
        return jsonify({"ok": bool(result.get("ok")), "result": result, "view": view})

    @app.post("/portal/api/data/reset")
    def portal_data_reset():
        body = _json_body()
        table_id = str(body.get("table_id") or "").strip() or None
        mode = str(body.get("mode") or "general").strip().lower()
        instance_id = str(body.get("instance_id") or "").strip() or None

        result = workspace.reset_staging(table_id=table_id)
        view = workspace.get_view(table_id, instance_id=instance_id, mode=mode) if table_id else None
        return jsonify({"ok": bool(result.get("ok")), "result": result, "view": view})

    @app.post("/portal/api/data/commit")
    def portal_data_commit():
        body = _json_body()
        table_id = str(body.get("table_id") or "").strip() or None
        mode = str(body.get("mode") or "general").strip().lower()
        instance_id = str(body.get("instance_id") or "").strip() or None

        result = workspace.commit(table_id=table_id)
        view = workspace.get_view(table_id, instance_id=instance_id, mode=mode) if table_id else None
        return jsonify({"ok": bool(result.get("ok")), "result": result, "view": view})

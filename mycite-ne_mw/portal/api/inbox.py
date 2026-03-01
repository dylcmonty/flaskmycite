from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from flask import abort, jsonify, make_response, request

from portal.services.request_log_store import append_event, read_events


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


def register_inbox_routes(
    app,
    *,
    private_dir: Path,
    options_private_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
):
    """Register minimal request-log (inbox) endpoints.

    Endpoints (portal-only later; currently open in local dev):
    - GET     /portal/api/inbox?msn_id=...&limit=100&offset=0&reverse=1
    - POST    /portal/api/inbox?msn_id=...   (JSON body = event)
    - OPTIONS /portal/api/inbox

    Notes:
    - This is an *operational log* store. Do not put secrets here.
    - Later, external signed submissions should go to a public endpoint
      (e.g., /api/inbox/<msn_id>) and then be validated before appending.
    """

    @app.get("/portal/api/inbox")
    def inbox_list():
        msn_id = (request.args.get("msn_id") or "").strip()
        if not msn_id:
            abort(400, description="Missing required query param: msn_id")

        limit = _as_int(request.args.get("limit"), 100, min_value=1, max_value=2000)
        offset = _as_int(request.args.get("offset"), 0, min_value=0, max_value=10_000_000)
        reverse = (request.args.get("reverse") or "1").strip() not in ("0", "false", "False")

        rr = read_events(private_dir, msn_id, limit=limit, offset=offset, reverse=reverse)

        out: Dict[str, Any] = {
            "schema": "mycite.inbox.v0",
            "msn_id": msn_id,
            "events": rr.events,
            "meta": {
                "limit": limit,
                "offset": offset,
                "reverse": reverse,
                "total_lines": rr.total_lines,
                "parse_errors": rr.parse_errors,
            },
        }
        if options_private_fn is not None:
            out["options_private"] = options_private_fn(msn_id)

        return jsonify(out)

    @app.post("/portal/api/inbox")
    def inbox_append():
        msn_id = (request.args.get("msn_id") or "").strip()
        if not msn_id:
            abort(400, description="Missing required query param: msn_id")

        if not request.is_json:
            abort(415, description="Expected application/json body")

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400, description="Expected JSON object body")

        try:
            path = append_event(private_dir, msn_id, body)
        except ValueError as e:
            abort(400, description=str(e))
        return jsonify({"ok": True, "msn_id": msn_id, "written_to": str(path)})

    @app.route("/portal/api/inbox", methods=["OPTIONS"])
    def inbox_options():
        resp = make_response("", 204)
        resp.headers["Allow"] = "GET, POST, OPTIONS"
        return resp

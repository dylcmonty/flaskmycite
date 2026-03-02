from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from flask import abort, jsonify, make_response, request

from portal.services.progeny_config_store import get_config


def register_progeny_config_routes(
    app,
    *,
    config_dir: Optional[Path] = None,
    options_private_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
):
    @app.get("/portal/api/progeny_config/<progeny_type>")
    def progeny_config_get(progeny_type: str):
        msn_id = (request.args.get("msn_id") or "").strip()
        try:
            cfg = get_config(progeny_type, config_dir=config_dir)
        except ValueError as e:
            abort(400, description=str(e))
        except FileNotFoundError as e:
            abort(404, description=str(e))

        out: Dict[str, Any] = {
            "schema": "mycite.progeny.config.v0",
            "progeny_type": str(cfg.get("progeny_type") or progeny_type),
            "config": cfg,
        }
        if msn_id:
            out["msn_id"] = msn_id
        if options_private_fn is not None and msn_id:
            out["options_private"] = options_private_fn(msn_id)
        return jsonify(out)

    @app.route("/portal/api/progeny_config/<progeny_type>", methods=["OPTIONS"])
    def progeny_config_options(progeny_type: str):
        _ = progeny_type
        resp = make_response("", 204)
        resp.headers["Allow"] = "GET, OPTIONS"
        return resp

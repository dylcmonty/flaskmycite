from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from flask import abort, jsonify, make_response, request


FORBIDDEN_SECRET_KEYS = {
    "private_key", "private_key_pem", "secret", "token", "password",
    "symmetric_key", "hmac_key", "hmac_key_b64", "api_key",
}


def _config_path(private_dir: Path, msn_id: str) -> Path:
    return private_dir / f"mycite-config-{msn_id}.json"


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _reject_obvious_secrets(obj: Dict[str, Any]) -> None:
    bad = set(obj.keys()).intersection(FORBIDDEN_SECRET_KEYS)
    if bad:
        abort(400, description=f"Do not store secrets in config JSON. Forbidden keys: {sorted(bad)}")


def register_config_routes(
    app,
    *,
    private_dir: Path,
    options_private_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
):
    """Register portal-only config endpoints.

    Storage:
      private/mycite-config-<msn_id>.json

    Endpoints:
    - GET     /portal/api/config?msn_id=...
    - PUT     /portal/api/config?msn_id=...   (overwrite file; prototype convenience)
    - OPTIONS /portal/api/config
    """

    @app.get("/portal/api/config")
    def portal_config_get():
        msn_id = (request.args.get("msn_id") or "").strip()
        if not msn_id:
            abort(400, description="Missing required query param: msn_id")

        p = _config_path(private_dir, msn_id)
        if not p.exists():
            abort(404, description=f"No config JSON found for msn_id={msn_id}")

        cfg = _read_json(p)
        if options_private_fn is not None:
            cfg["options_private"] = options_private_fn(msn_id)
        return jsonify(cfg)

    @app.put("/portal/api/config")
    def portal_config_put():
        msn_id = (request.args.get("msn_id") or "").strip()
        if not msn_id:
            abort(400, description="Missing required query param: msn_id")

        if not request.is_json:
            abort(415, description="Expected application/json body")

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400, description="Expected JSON object body")

        _reject_obvious_secrets(body)

        body = dict(body)
        body["updated_unix_ms"] = int(time.time() * 1000)

        p = _config_path(private_dir, msn_id)
        _write_json(p, body)
        return jsonify({"ok": True, "msn_id": msn_id, "written_to": str(p)})

    @app.route("/portal/api/config", methods=["OPTIONS"])
    def portal_config_options():
        resp = make_response("", 204)
        resp.headers["Allow"] = "GET, PUT, OPTIONS"
        return resp

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from flask import abort, jsonify, make_response, request


def _config_path(private_dir: Path, msn_id: str) -> Path:
    return private_dir / f"mycite-config-{msn_id}.json"


def _aliases_dir(private_dir: Path) -> Path:
    return private_dir / "aliases"


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_alias_path(private_dir: Path, alias_filename: str) -> Optional[Path]:
    candidates = [
        _aliases_dir(private_dir) / alias_filename,
        private_dir / alias_filename,  # fallback
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


def register_aliases_routes(
    app,
    *,
    private_dir: Path,
    options_private_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
):
    """Register portal-only aliases endpoints.

    Aliases are listed in:
      private/mycite-config-<msn_id>.json -> "aliases": [{<counterparty_msn_id>: <alias_filename>}, ...]

    Alias files live in:
      private/aliases/<alias_filename>

    Endpoints:
    - GET     /portal/api/aliases?msn_id=...
    - OPTIONS /portal/api/aliases
    """

    @app.get("/portal/api/aliases")
    def portal_aliases_get():
        msn_id = (request.args.get("msn_id") or "").strip()
        if not msn_id:
            abort(400, description="Missing required query param: msn_id")

        cfg_p = _config_path(private_dir, msn_id)
        if not cfg_p.exists():
            abort(404, description=f"No config JSON found for msn_id={msn_id}")

        cfg = _read_json(cfg_p)
        aliases = cfg.get("aliases", [])

        resolved: Dict[str, Any] = {}
        errors: Dict[str, str] = {}

        for entry in aliases:
            if not isinstance(entry, dict):
                continue
            for counterpart_msn_id, alias_filename in entry.items():
                alias_path = _resolve_alias_path(private_dir, alias_filename)
                if not alias_path:
                    errors[counterpart_msn_id] = f"Missing alias file: {alias_filename}"
                    continue
                try:
                    resolved[counterpart_msn_id] = _read_json(alias_path)
                except Exception as e:
                    errors[counterpart_msn_id] = f"Failed to read alias file {alias_filename}: {e}"

        out: Dict[str, Any] = {
            "msn_id": msn_id,
            "schema": "mycite.alias.bundle.v0",
            "aliases": resolved,
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

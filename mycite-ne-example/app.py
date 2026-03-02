import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from flask import Flask, abort, jsonify, make_response, render_template, request
from jinja2 import TemplateNotFound

from data.engine.workspace import Workspace
from data.storage_json import JsonStorageBackend
from portal.api.aliases import register_aliases_routes
from portal.api.config import register_config_routes
from portal.api.contracts import register_contract_routes
from portal.api.data_workspace import register_data_routes
from portal.api.inbox import register_inbox_routes
from portal.api.magnetlinks import register_magnetlinks_routes
from portal.api.progeny_config import register_progeny_config_routes
from portal.api.public_inbox import register_public_inbox_routes
from portal.services.policy import is_external_signed_path, is_portal_path, is_public_path
from portal.tools.runtime import read_enabled_tools, register_tool_blueprints

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "portal", "ui", "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "portal", "ui", "static"),
    static_url_path="/portal/static",
)

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = Path(os.environ.get("PUBLIC_DIR", str(BASE_DIR / "public")))
PRIVATE_DIR = Path(os.environ.get("PRIVATE_DIR", str(BASE_DIR / "private")))
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR / "data")))
FALLBACK_DIR = BASE_DIR

AUTH_MODE = os.environ.get("AUTH_MODE", "none")  # none | keycloak (later)


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to parse JSON at {path}: {e}") from e

    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected object JSON in {path}")
    return payload


def _find_first(paths) -> Optional[Path]:
    for p in paths:
        if p.exists() and p.is_file():
            return p
    return None


def _resolve_public_profile_path(msn_id: str) -> Optional[Path]:
    candidates = [
        PUBLIC_DIR / f"{msn_id}.json",
        PUBLIC_DIR / f"msn-{msn_id}.json",
        PUBLIC_DIR / f"mss-{msn_id}.json",
        FALLBACK_DIR / f"{msn_id}.json",
        FALLBACK_DIR / f"msn-{msn_id}.json",
        FALLBACK_DIR / f"mss-{msn_id}.json",
    ]
    return _find_first(candidates)


def _options_public(msn_id: str) -> Dict[str, Any]:
    return {
        "self": {
            "href": f"/{msn_id}.json",
            "methods": ["GET", "OPTIONS"],
            "auth": "none",
        }
    }


def _options_private(msn_id: str) -> Dict[str, Any]:
    return {
        "portal": {"href": "/portal", "methods": ["GET", "OPTIONS"], "auth": "keycloak_or_local"},
        "config": {
            "href": f"/portal/api/config?msn_id={msn_id}",
            "methods": ["GET", "PUT", "OPTIONS"],
            "auth": "keycloak_or_local",
        },
        "aliases": {
            "href": f"/portal/api/aliases?msn_id={msn_id}",
            "methods": ["GET", "OPTIONS"],
            "auth": "keycloak_or_local",
        },
        "inbox": {
            "href": f"/portal/api/inbox?msn_id={msn_id}",
            "methods": ["GET", "POST", "OPTIONS"],
            "auth": "keycloak_or_local",
        },
        "contracts": {
            "href": f"/portal/api/contracts?msn_id={msn_id}",
            "methods": ["GET", "POST", "OPTIONS"],
            "auth": "keycloak_or_local",
        },
        "magnetlinks": {
            "href": f"/portal/api/magnetlinks?msn_id={msn_id}",
            "methods": ["GET", "POST", "OPTIONS"],
            "auth": "keycloak_or_local",
        },
        "progeny_config": {
            "href": f"/portal/api/progeny_config/tenant?msn_id={msn_id}",
            "methods": ["GET", "OPTIONS"],
            "auth": "keycloak_or_local",
        },
    }


def _infer_local_msn_id() -> str:
    if os.environ.get("MSN_ID"):
        return str(os.environ.get("MSN_ID")).strip()

    for cfg in sorted(PRIVATE_DIR.glob("mycite-config-*.json")):
        try:
            payload = _read_json(cfg)
        except Exception:
            continue
        msn_id = str(payload.get("msn_id") or "").strip()
        if msn_id:
            return msn_id

    for path in sorted(PUBLIC_DIR.glob("*.json")):
        try:
            payload = _read_json(path)
        except Exception:
            continue
        msn_id = str(payload.get("msn_id") or "").strip()
        if msn_id:
            return msn_id

    return ""


MSN_ID = _infer_local_msn_id()
TOOL_TABS = register_tool_blueprints(app, read_enabled_tools(PRIVATE_DIR, msn_id=MSN_ID or None))
DATA_WORKSPACE = Workspace(JsonStorageBackend(DATA_DIR), config={})


def _format_sidebar_entity_title(raw: str) -> str:
    token = re.sub(r"[_-]+", " ", str(raw or "").strip())
    token = re.sub(r"\s+", " ", token).strip()
    return token.upper()


def _alias_label(alias_payload: Dict[str, Any], alias_id: Optional[str] = None) -> str:
    host_title = str(alias_payload.get("host_title") or "").strip()
    if host_title:
        return _format_sidebar_entity_title(host_title)

    if alias_id:
        return _format_sidebar_entity_title(alias_id)

    return "UNNAMED ALIAS"
def list_aliases_ne(private_dir: Path) -> list[Dict[str, Any]]:
    aliases_dir = private_dir / "aliases"
    if not aliases_dir.exists() or not aliases_dir.is_dir():
        return []

    aliases: list[Dict[str, Any]] = []
    for alias_path in sorted(aliases_dir.glob("*.json")):
        if not alias_path.is_file():
            continue
        try:
            alias_payload = _read_json(alias_path)
        except Exception:
            continue

        aliases.append(
                {
                    "alias_id": alias_path.stem,
                    "label": _alias_label(alias_payload, alias_path.stem),
                    "org_title": str(alias_payload.get("host_title") or "").strip(),
                    "org_msn_id": str(alias_payload.get("alias_host") or "").strip(),
                }
        )
    return aliases


def load_alias_ne(private_dir: Path, alias_id: str) -> Dict[str, Any]:
    normalized_alias_id = (alias_id or "").strip()
    if (
        not normalized_alias_id
        or "/" in normalized_alias_id
        or "\\" in normalized_alias_id
        or ".." in normalized_alias_id
    ):
        raise ValueError("alias_id must be a stable identifier, not a path")

    alias_path = private_dir / "aliases" / f"{normalized_alias_id}.json"
    if not alias_path.exists() or not alias_path.is_file():
        raise FileNotFoundError(f"No alias record found for alias_id={normalized_alias_id}")
    return _read_json(alias_path)


def _sanitize_env_suffix(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", value).upper()


def _resolve_embed_port(alias_host: str) -> str:
    host = (alias_host or "").strip()
    if host:
        per_host_key = f"EMBED_HOST_PORT_{_sanitize_env_suffix(host)}"
        if os.environ.get(per_host_key):
            return str(os.environ.get(per_host_key)).strip()

    if os.environ.get("EMBED_HOST_PORT"):
        return str(os.environ.get("EMBED_HOST_PORT")).strip()

    return "5001"


def _extract_tenant_msn_id(alias_payload: Dict[str, Any]) -> str:
    return str(alias_payload.get("child_msn_id") or alias_payload.get("tenant_id") or "").strip()


def _extract_contract_id(alias_payload: Dict[str, Any]) -> str:
    return str(alias_payload.get("contract_id") or alias_payload.get("symmetric_key_contract") or "").strip()


def _extract_member_msn_id(alias_payload: Dict[str, Any]) -> str:
    return str(
        alias_payload.get("member_msn_id")
        or alias_payload.get("child_msn_id")
        or alias_payload.get("tenant_id")
        or alias_payload.get("msn_id")
        or ""
    ).strip()


def _build_widget_url(alias_id: str, alias_payload: Dict[str, Any]) -> str:
    org_msn_id = str(alias_payload.get("alias_host") or "").strip()
    org_title = str(alias_payload.get("host_title") or "").strip()
    base_url = f"http://127.0.0.1:{_resolve_embed_port(org_msn_id)}"

    progeny_type = str(alias_payload.get("progeny_type") or "").strip().lower()
    tenant_msn_id = _extract_tenant_msn_id(alias_payload)
    if progeny_type == "tenant" and tenant_msn_id:
        query = urlencode(
            {
                "tenant_msn_id": tenant_msn_id,
                "contract_id": _extract_contract_id(alias_payload),
                "as_alias_id": alias_id,
            }
        )
        return f"{base_url}/portal/embed/tenant?{query}"

    member_msn_id = _extract_member_msn_id(alias_payload)
    if progeny_type == "board_member" and member_msn_id:
        query = urlencode({"member_msn_id": member_msn_id, "as_alias_id": alias_id, "tab": "streams"})
        return f"{base_url}/portal/embed/board_member?{query}"

    query = urlencode({"org_msn_id": org_msn_id, "as_alias_id": alias_id, "org_title": org_title})
    return f"{base_url}/portal/embed/poc?{query}"


def _sanitize_public_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {"msn_id", "schema", "title", "public_key", "entity_type", "accessible"}
    out = {k: payload.get(k) for k in allowed if k in payload}
    out.setdefault("accessible", {})
    return out


def require_auth_if_enabled() -> None:
    if AUTH_MODE == "none":
        return
    if AUTH_MODE == "keycloak":
        raise RuntimeError("AUTH_MODE=keycloak set but token verification not implemented")
    raise RuntimeError(f"Unknown AUTH_MODE={AUTH_MODE}")


@app.before_request
def enforce_boundaries() -> None:
    path = request.path
    if is_portal_path(path):
        require_auth_if_enabled()
    elif is_external_signed_path(path):
        return
    elif is_public_path(path):
        return


@app.get("/<msn_id>.json")
def public_contact_card(msn_id: str):
    path = _resolve_public_profile_path(msn_id)
    if not path:
        abort(404, description=f"No public profile JSON found for msn_id={msn_id}")

    raw = _read_json(path)
    limited = _sanitize_public_profile(raw)
    limited["options_public"] = _options_public(msn_id)
    return jsonify(limited)


@app.route("/<msn_id>.json", methods=["OPTIONS"])
def public_contact_card_options(msn_id: str):
    resp = make_response(jsonify({"msn_id": msn_id, "options_public": _options_public(msn_id)}), 200)
    resp.headers["Allow"] = "GET, OPTIONS"
    return resp


@app.get("/portal")
def portal_home():
    aliases = list_aliases_ne(PRIVATE_DIR)
    try:
        return render_template("home.html", aliases=aliases, tool_tabs=TOOL_TABS)
    except TemplateNotFound:
        return (
            "<h1>MyCite Portal</h1>"
            "<p>Local dev portal (AUTH_MODE=none). Later this path is Keycloak-protected.</p>"
            "<p>UI shell not installed yet (home.html missing). Using fallback.</p>"
        )


@app.route("/portal", methods=["OPTIONS"])
def portal_options():
    resp = make_response("", 204)
    resp.headers["Allow"] = "GET, OPTIONS"
    return resp


@app.get("/portal/alias/<alias_id>")
def portal_alias_session(alias_id: str):
    aliases = list_aliases_ne(PRIVATE_DIR)
    try:
        alias_payload = load_alias_ne(PRIVATE_DIR, alias_id)
    except (FileNotFoundError, ValueError):
        abort(404, description=f"No alias record found for alias_id={alias_id}")

    org_msn_id = str(alias_payload.get("alias_host") or "").strip()
    org_title = str(alias_payload.get("host_title") or "").strip()
    progeny_type = str(alias_payload.get("progeny_type") or "").strip().lower()
    tenant_id = _extract_tenant_msn_id(alias_payload)
    org_widget_url = _build_widget_url(alias_id, alias_payload)

    return render_template(
        "alias_shell.html",
        aliases=aliases,
        active_alias_id=alias_id,
        alias_label=_alias_label(alias_payload, alias_id),
        org_title=org_title,
        org_msn_id=org_msn_id,
        org_widget_url=org_widget_url,
        msn_id=str(alias_payload.get("msn_id") or "").strip(),
        alias_progeny_type=progeny_type,
        alias_tenant_id=tenant_id,
    )


register_config_routes(app, private_dir=PRIVATE_DIR, options_private_fn=_options_private)
register_aliases_routes(app, private_dir=PRIVATE_DIR, options_private_fn=_options_private)
register_inbox_routes(app, private_dir=PRIVATE_DIR, options_private_fn=_options_private)
register_contract_routes(app, private_dir=PRIVATE_DIR, options_private_fn=_options_private)
register_magnetlinks_routes(app, private_dir=PRIVATE_DIR, options_private_fn=_options_private)
register_progeny_config_routes(app, options_private_fn=_options_private)
register_public_inbox_routes(app, private_dir=PRIVATE_DIR, public_dir=PUBLIC_DIR, data_dir=DATA_DIR)
register_data_routes(
    app,
    workspace=DATA_WORKSPACE,
    aliases_provider=lambda: list_aliases_ne(PRIVATE_DIR),
    options_private_fn=_options_private,
    msn_id_provider=lambda: MSN_ID,
)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

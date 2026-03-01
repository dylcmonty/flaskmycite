import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from flask import Flask, abort, jsonify, make_response, render_template, request
from jinja2 import TemplateNotFound

from portal.api.aliases import register_aliases_routes
from portal.api.config import register_config_routes
from portal.api.contracts import register_contract_routes
from portal.api.inbox import register_inbox_routes
from portal.api.magnetlinks import register_magnetlinks_routes
from portal.api.public_inbox import register_public_inbox_routes
from portal.services.policy import is_external_signed_path, is_portal_path, is_public_path

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
    }


def _alias_label(alias_payload: Dict[str, Any], alias_id: Optional[str] = None) -> str:
    given_name = str(alias_payload.get("given_name") or "").strip()
    family_name = str(alias_payload.get("family_name") or "").strip()
    combined = " ".join(part for part in (given_name, family_name) if part).strip()
    if combined:
        return combined

    host_title = str(alias_payload.get("host_title") or "").strip()
    if host_title:
        return host_title

    if alias_id:
        return alias_id
    return "Unnamed alias"


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
        return render_template("home.html", aliases=aliases)
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
    widget_base_url = os.environ.get("ORG_WIDGET_BASE_URL", "http://127.0.0.1:5001/portal/embed/poc")
    org_widget_url = (
        f"{widget_base_url}?"
        f"{urlencode({'org_msn_id': org_msn_id, 'as_alias_id': alias_id, 'org_title': org_title})}"
    )

    return render_template(
        "alias_shell.html",
        aliases=aliases,
        active_alias_id=alias_id,
        alias_label=_alias_label(alias_payload, alias_id),
        org_title=org_title,
        org_msn_id=org_msn_id,
        org_widget_url=org_widget_url,
        msn_id=str(alias_payload.get("msn_id") or "").strip(),
    )


register_config_routes(app, private_dir=PRIVATE_DIR, options_private_fn=_options_private)
register_aliases_routes(app, private_dir=PRIVATE_DIR, options_private_fn=_options_private)
register_inbox_routes(app, private_dir=PRIVATE_DIR, options_private_fn=_options_private)
register_contract_routes(app, private_dir=PRIVATE_DIR, options_private_fn=_options_private)
register_magnetlinks_routes(app, private_dir=PRIVATE_DIR, options_private_fn=_options_private)
register_public_inbox_routes(app, private_dir=PRIVATE_DIR, public_dir=PUBLIC_DIR, data_dir=DATA_DIR)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

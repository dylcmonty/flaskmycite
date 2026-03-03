import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from flask import Flask, abort, jsonify, make_response, redirect, render_template, request
from jinja2 import TemplateNotFound

from data.data import list_table_catalog, register_data_routes as register_legacy_data_routes
from data.engine.workspace import Workspace
from data.storage_json import JsonStorageBackend
from portal.api.aliases import get_alias_record, list_alias_records, register_aliases_routes
from portal.api.config import register_config_routes
from portal.api.contracts import register_contract_routes
from portal.api.data_workspace import register_data_routes as register_data_workspace_routes
from portal.api.inbox import register_inbox_routes
from portal.api.magnetlinks import register_magnetlinks_routes
from portal.api.progeny_config import register_progeny_config_routes
from portal.services.alias_factory import alias_path, client_key_for_msn, merge_field_names
from portal.services.progeny_config_store import get_client_config, get_config
from portal.services.request_log_store import append_event
from portal.services.tenant_progeny_store import load_profile, save_profile, set_paypal_config
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


for required in (
    PRIVATE_DIR / "contracts",
    PRIVATE_DIR / "request_log",
    PRIVATE_DIR / "aliases",
    PRIVATE_DIR / "progeny" / "tenant",
    PRIVATE_DIR / "vault" / "contracts",
    DATA_DIR / "cache" / "contacts",
    DATA_DIR / "cache" / "tenant",
):
    required.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected object JSON in {path}")
    return payload


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _find_first(paths) -> Optional[Path]:
    for path in paths:
        if path.exists() and path.is_file():
            return path
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


def _sanitize_public_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {"msn_id", "schema", "title", "public_key", "entity_type", "accessible"}
    out = {k: payload.get(k) for k in allowed if k in payload}
    out.setdefault("accessible", {})
    return out


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
        "clients": {"href": "/portal/clients", "methods": ["GET", "OPTIONS"], "auth": "keycloak_or_local"},
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
        "paypal_demo_update": {
            "href": f"/portal/api/tools/paypal_demo/update?msn_id={msn_id}",
            "methods": ["POST", "OPTIONS"],
            "auth": "keycloak_or_local",
        },
        "paypal_demo_confirm": {
            "href": f"/portal/api/tools/paypal_demo/confirm?msn_id={msn_id}",
            "methods": ["POST", "OPTIONS"],
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
    embed_port = _resolve_embed_port(org_msn_id)
    base_url = f"http://127.0.0.1:{embed_port}"

    progeny_type = str(alias_payload.get("progeny_type") or "").strip().lower()
    tenant_id = _extract_tenant_msn_id(alias_payload)
    if progeny_type == "tenant" and tenant_id:
        query = urlencode(
            {
                "tenant_msn_id": tenant_id,
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


def list_aliases_for_sidebar(private_dir: Path) -> list[Dict[str, Any]]:
    records, _ = list_alias_records(private_dir)
    aliases: list[Dict[str, Any]] = []
    for record in records:
        alias_id = str(record.get("alias_id") or "").strip()
        if not alias_id:
            continue
        aliases.append(
            {
                "alias_id": alias_id,
                "label": _alias_label(record, alias_id),
                "org_title": str(record.get("host_title") or "").strip(),
                "org_msn_id": str(record.get("alias_host") or "").strip(),
                "progeny_type": str(record.get("progeny_type") or "").strip(),
                "tenant_id": str(record.get("child_msn_id") or record.get("tenant_id") or "").strip(),
            }
        )
    return aliases


def _field_names_for_alias(alias_payload: Dict[str, Any]) -> list[str]:
    progeny_type = str(alias_payload.get("progeny_type") or "").strip()
    if not progeny_type:
        return []

    base_fields = []
    try:
        cfg = get_config(progeny_type)
        if isinstance(cfg.get("fields"), list):
            base_fields = cfg.get("fields") or []
    except Exception:
        base_fields = []

    overlay_fields = []
    client_key = client_key_for_msn(str(alias_payload.get("client_msn_id") or ""))
    if client_key:
        overlay = get_client_config(client_key)
        if isinstance(overlay, dict) and isinstance(overlay.get("fields"), list):
            overlay_fields = overlay.get("fields") or []

    existing_fields = alias_payload.get("fields") if isinstance(alias_payload.get("fields"), dict) else {}
    return merge_field_names(base_fields, overlay_fields, existing_fields.keys())


MSN_ID = _infer_local_msn_id()


def _load_active_private_config() -> Dict[str, Any]:
    candidates: list[Path] = []
    if MSN_ID:
        candidates.append(PRIVATE_DIR / f"mycite-config-{MSN_ID}.json")
    candidates.extend(sorted(PRIVATE_DIR.glob("mycite-config-*.json")))

    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if not path.exists() or not path.is_file():
            continue
        try:
            payload = _read_json(path)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


ACTIVE_PRIVATE_CONFIG = _load_active_private_config()
DATA_TOOL_CONFIG = (
    ACTIVE_PRIVATE_CONFIG.get("data_tool")
    if isinstance(ACTIVE_PRIVATE_CONFIG.get("data_tool"), dict)
    else {}
)
WORKSPACE_CONFIG: Dict[str, Any] = dict(DATA_TOOL_CONFIG)
WORKSPACE_CONFIG["state_path"] = str(PRIVATE_DIR / "daemon_state" / "data_workspace.json")

TOOL_TABS = register_tool_blueprints(app, read_enabled_tools(PRIVATE_DIR, msn_id=MSN_ID or None))
DATA_WORKSPACE = Workspace(JsonStorageBackend(DATA_DIR), config=WORKSPACE_CONFIG)


@app.get("/<msn_id>.json")
def public_contact_card(msn_id: str):
    path = _resolve_public_profile_path(msn_id)
    if not path:
        abort(404, description=f"No public profile JSON found for msn_id={msn_id}")

    payload = _sanitize_public_profile(_read_json(path))
    payload["options_public"] = _options_public(msn_id)
    return jsonify(payload)


@app.route("/<msn_id>.json", methods=["OPTIONS"])
def public_contact_card_options(msn_id: str):
    resp = make_response(jsonify({"msn_id": msn_id, "options_public": _options_public(msn_id)}), 200)
    resp.headers["Allow"] = "GET, OPTIONS"
    return resp


@app.get("/portal")
def portal_home():
    aliases = list_aliases_for_sidebar(PRIVATE_DIR)
    try:
        return render_template(
            "home.html",
            aliases=aliases,
            msn_id=MSN_ID,
            data_tables=list_table_catalog(),
            tool_tabs=TOOL_TABS,
        )
    except TemplateNotFound:
        return "<h1>MyCite Portal</h1><p>home.html missing</p>"


@app.route("/portal", methods=["OPTIONS"])
def portal_options():
    resp = make_response("", 204)
    resp.headers["Allow"] = "GET, OPTIONS"
    return resp


@app.get("/portal/alias/<alias_id>")
def portal_alias_session(alias_id: str):
    aliases = list_aliases_for_sidebar(PRIVATE_DIR)
    try:
        alias_payload = get_alias_record(PRIVATE_DIR, alias_id)
    except (FileNotFoundError, ValueError):
        abort(404, description=f"No alias record found for alias_id={alias_id}")

    tenant_id = str(alias_payload.get("child_msn_id") or alias_payload.get("tenant_id") or "").strip()
    progeny_type = str(alias_payload.get("progeny_type") or "").strip().lower()

    return render_template(
        "alias_shell.html",
        aliases=aliases,
        active_alias_id=alias_id,
        alias_label=_alias_label(alias_payload, alias_id),
        org_title=str(alias_payload.get("host_title") or "").strip(),
        org_msn_id=str(alias_payload.get("alias_host") or "").strip(),
        org_widget_url=_build_widget_url(alias_id, alias_payload),
        msn_id=str(alias_payload.get("msn_id") or "").strip() or MSN_ID,
        alias_progeny_type=progeny_type,
        alias_tenant_id=tenant_id,
    )


@app.get("/portal/clients")
def portal_clients():
    aliases = list_aliases_for_sidebar(PRIVATE_DIR)
    records, _ = list_alias_records(PRIVATE_DIR)

    rows = []
    for record in records:
        progeny_type = str(record.get("progeny_type") or "").strip().lower()
        if not progeny_type:
            continue
        if progeny_type != "tenant" and not progeny_type.startswith("client_"):
            continue

        alias_id = str(record.get("alias_id") or "").strip()
        if not alias_id:
            continue

        rows.append(
            {
                "alias_id": alias_id,
                "client_msn_id": str(record.get("client_msn_id") or record.get("alias_host") or "").strip(),
                "progeny_type": progeny_type,
                "status": str(record.get("status") or "active").strip(),
            }
        )

    return render_template("clients.html", aliases=aliases, client_aliases=rows, msn_id=MSN_ID)


@app.get("/portal/client/<alias_id>")
def portal_client_detail(alias_id: str):
    aliases = list_aliases_for_sidebar(PRIVATE_DIR)
    try:
        alias_payload = get_alias_record(PRIVATE_DIR, alias_id)
    except (FileNotFoundError, ValueError):
        abort(404, description=f"No alias record found for alias_id={alias_id}")

    progeny_type = str(alias_payload.get("progeny_type") or "").strip().lower()
    fields = alias_payload.get("fields") if isinstance(alias_payload.get("fields"), dict) else {}

    return render_template(
        "client_detail.html",
        aliases=aliases,
        alias_id=alias_id,
        alias_payload=alias_payload,
        progeny_type=progeny_type,
        fields=fields,
        field_names=_field_names_for_alias(alias_payload),
        save_ok=False,
        msn_id=MSN_ID,
    )


@app.post("/portal/client/<alias_id>")
def portal_client_detail_save(alias_id: str):
    aliases = list_aliases_for_sidebar(PRIVATE_DIR)
    try:
        alias_payload = get_alias_record(PRIVATE_DIR, alias_id)
    except (FileNotFoundError, ValueError):
        abort(404, description=f"No alias record found for alias_id={alias_id}")

    fields = alias_payload.get("fields") if isinstance(alias_payload.get("fields"), dict) else {}
    fields = dict(fields)
    field_names = _field_names_for_alias(alias_payload)
    for name in field_names:
        fields[name] = (request.form.get(f"field_{name}") or "").strip()

    alias_payload["fields"] = fields
    _write_json(alias_path(PRIVATE_DIR, alias_id), alias_payload)

    return render_template(
        "client_detail.html",
        aliases=aliases,
        alias_id=alias_id,
        alias_payload=alias_payload,
        progeny_type=str(alias_payload.get("progeny_type") or "").strip().lower(),
        fields=fields,
        field_names=field_names,
        save_ok=True,
        msn_id=MSN_ID,
    )


@app.get("/portal/embed/poc")
def portal_embed_poc():
    org_msn_id = (request.args.get("org_msn_id") or "").strip()
    as_alias_id = (request.args.get("as_alias_id") or "").strip()
    org_title = (request.args.get("org_title") or "").strip()
    if not org_title and org_msn_id:
        org_title = f"Organization {org_msn_id}"

    return render_template(
        "embed_poc.html",
        org_msn_id=org_msn_id,
        as_alias_id=as_alias_id,
        org_title=org_title,
    )


_CONTRACT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _is_usable_contract_id(contract_id: str) -> bool:
    token = (contract_id or "").strip()
    if not token or not _CONTRACT_ID_RE.fullmatch(token):
        return False
    lowered = token.lower()
    if "placeholder" in lowered:
        return False
    if lowered.startswith("symmetric_key_contracts_ref_"):
        return False
    return True


def _resolve_tenant_embed_params() -> Dict[str, str]:
    tenant_msn_id = (request.values.get("tenant_msn_id") or request.values.get("tenant_id") or "").strip()
    contract_id = (request.values.get("contract_id") or "").strip()
    as_alias_id = (request.values.get("as_alias_id") or request.values.get("alias_id") or "").strip()
    tab = (request.values.get("tab") or "").strip().lower() or "payments"
    theme = (request.values.get("theme") or "paper").strip().lower() or "paper"
    if tab not in {"payments", "agreement", "analytics", "blog"}:
        tab = "payments"

    alias_payload: Dict[str, Any] = {}
    if as_alias_id:
        try:
            alias_payload = get_alias_record(PRIVATE_DIR, as_alias_id)
        except Exception:
            alias_payload = {}

    if not tenant_msn_id and alias_payload:
        tenant_msn_id = _extract_tenant_msn_id(alias_payload)
    if not contract_id and alias_payload:
        contract_id = _extract_contract_id(alias_payload)

    return {
        "tenant_msn_id": tenant_msn_id,
        "contract_id": contract_id,
        "as_alias_id": as_alias_id,
        "tab": tab,
        "theme": theme,
    }


def _normalize_event_mask(raw_values: list[str]) -> list[str]:
    out: list[str] = []
    seen = set()
    for raw in raw_values:
        parts = str(raw or "").split(",")
        for part in parts:
            token = part.strip()
            if not token or token in seen:
                continue
            seen.add(token)
            out.append(token)
    return out or ["PAYMENT.CAPTURE.COMPLETED"]


def _tenant_redirect(params: Dict[str, str], **extra: str):
    query: Dict[str, str] = {
        "tenant_msn_id": params.get("tenant_msn_id", ""),
        "contract_id": params.get("contract_id", ""),
        "as_alias_id": params.get("as_alias_id", ""),
        "tab": "payments",
        "theme": params.get("theme", "paper"),
    }
    for key, value in extra.items():
        query[key] = str(value)
    return redirect(f"/portal/embed/tenant?{urlencode(query)}")


def _render_tenant_shell(*, force_tab: Optional[str] = None):
    params = _resolve_tenant_embed_params()
    if force_tab:
        params["tab"] = force_tab

    contract_usable = _is_usable_contract_id(params["contract_id"])
    tenant_msn_id = params["tenant_msn_id"]
    profile: Dict[str, Any] = {}
    warning = ""

    if not tenant_msn_id:
        warning = "Missing tenant_msn_id for tenant configuration."
    elif not contract_usable:
        warning = "A valid contract_id is required before saving tenant PayPal configuration."
    else:
        profile = load_profile(tenant_msn_id, params["contract_id"])

    paypal = profile.get("paypal") if isinstance(profile.get("paypal"), dict) else {}
    secret_enc = paypal.get("client_secret_enc") if isinstance(paypal.get("client_secret_enc"), dict) else {}
    has_encrypted_secret = bool(secret_enc.get("ciphertext_b64") and secret_enc.get("nonce_b64"))

    status = profile.get("status") if isinstance(profile.get("status"), dict) else {}
    append_event(
        PRIVATE_DIR,
        MSN_ID,
        {
            "type": "tenant.paypal.config.viewed",
            "status": "ok",
            "tenant_msn_id": tenant_msn_id,
            "contract_id": params["contract_id"],
            "details": {"tab": params["tab"]},
        },
    )

    return render_template(
        "tenant_embed_shell.html",
        theme=params["theme"],
        tab=params["tab"],
        tenant_msn_id=tenant_msn_id,
        contract_id=params["contract_id"],
        as_alias_id=params["as_alias_id"],
        contract_usable=contract_usable,
        warning=warning,
        profile=profile,
        paypal=paypal,
        status=status,
        has_encrypted_secret=has_encrypted_secret,
        saved=(request.args.get("saved") or "").strip() == "1",
        webhook=(request.args.get("webhook") or "").strip(),
    )


@app.get("/portal/embed/tenant")
def embed_tenant():
    return _render_tenant_shell()


@app.get("/portal/embed/tenant/payments")
def embed_tenant_payments():
    return _render_tenant_shell(force_tab="payments")


@app.post("/portal/embed/tenant/payments/paypal/save")
def embed_tenant_paypal_save():
    params = _resolve_tenant_embed_params()
    if not params["tenant_msn_id"] or not _is_usable_contract_id(params["contract_id"]):
        abort(400, description="A valid tenant_msn_id and contract_id are required")

    client_id = (request.form.get("paypal_client_id") or "").strip()
    client_secret_plain = request.form.get("paypal_client_secret") or ""
    webhook_target_url = (request.form.get("webhook_target_url") or "").strip()
    webhook_event_mask = _normalize_event_mask(request.form.getlist("webhook_event_mask"))

    profile = load_profile(params["tenant_msn_id"], params["contract_id"])
    profile = set_paypal_config(
        profile,
        client_id=client_id,
        client_secret_plain=client_secret_plain,
        target_url=webhook_target_url,
        event_mask=webhook_event_mask,
    )
    save_profile(profile)

    append_event(
        PRIVATE_DIR,
        MSN_ID,
        {
            "type": "tenant.paypal.config.saved",
            "status": "ok",
            "tenant_msn_id": params["tenant_msn_id"],
            "contract_id": params["contract_id"],
            "client_id": client_id,
            "details": {
                "webhook.target_url": webhook_target_url,
                "event_mask": webhook_event_mask,
            },
        },
    )
    return _tenant_redirect(params, saved="1")


@app.post("/portal/embed/tenant/payments/paypal/webhook/register")
def embed_tenant_paypal_webhook_register():
    params = _resolve_tenant_embed_params()
    if not params["tenant_msn_id"] or not _is_usable_contract_id(params["contract_id"]):
        abort(400, description="A valid tenant_msn_id and contract_id are required")

    webhook_target_url = (request.form.get("webhook_target_url") or "").strip()
    webhook_event_mask = _normalize_event_mask(request.form.getlist("webhook_event_mask"))
    append_event(
        PRIVATE_DIR,
        MSN_ID,
        {
            "type": "tenant.paypal.webhook.register.requested",
            "status": "requested",
            "tenant_msn_id": params["tenant_msn_id"],
            "contract_id": params["contract_id"],
            "details": {
                "webhook.target_url": webhook_target_url,
                "event_mask": webhook_event_mask,
            },
        },
    )

    try:
        # Stubbed for MVP; real provider registration will be added in a follow-up.
        append_event(
            PRIVATE_DIR,
            MSN_ID,
            {
                "type": "tenant.paypal.webhook.register.completed",
                "status": "completed",
                "tenant_msn_id": params["tenant_msn_id"],
                "contract_id": params["contract_id"],
                "details": {"webhook.target_url": webhook_target_url},
            },
        )
        return _tenant_redirect(params, webhook="registered")
    except Exception as exc:
        append_event(
            PRIVATE_DIR,
            MSN_ID,
            {
                "type": "tenant.paypal.webhook.register.failed",
                "status": "failed",
                "tenant_msn_id": params["tenant_msn_id"],
                "contract_id": params["contract_id"],
                "details": {"error": str(exc)},
            },
        )
        return _tenant_redirect(params, webhook="failed")


register_config_routes(app, private_dir=PRIVATE_DIR, options_private_fn=_options_private)
register_aliases_routes(app, private_dir=PRIVATE_DIR, options_private_fn=_options_private)
register_inbox_routes(app, private_dir=PRIVATE_DIR, options_private_fn=_options_private)
register_contract_routes(app, private_dir=PRIVATE_DIR, options_private_fn=_options_private)
register_magnetlinks_routes(app, private_dir=PRIVATE_DIR, options_private_fn=_options_private)
register_progeny_config_routes(app, options_private_fn=_options_private)
register_data_workspace_routes(
    app,
    workspace=DATA_WORKSPACE,
    aliases_provider=lambda: list_aliases_for_sidebar(PRIVATE_DIR),
    options_private_fn=_options_private,
    msn_id_provider=lambda: MSN_ID,
    include_home_redirect=False,
    include_legacy_shims=False,
)
register_legacy_data_routes(app, aliases_provider=lambda: list_aliases_for_sidebar(PRIVATE_DIR))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)

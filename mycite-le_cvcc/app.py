import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from flask import Flask, abort, jsonify, make_response, redirect, render_template, request
from jinja2 import TemplateNotFound

from portal.api.aliases import get_alias_record, list_alias_records, register_aliases_routes
from portal.services.board_access import require_board_member
from portal.services.request_log_store import append_event as append_request_log_event
from portal.services.workspace_store import append_event as append_workspace_event
from portal.services.workspace_store import materialize_people, read_events, workspace_root
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
FALLBACK_DIR = BASE_DIR
BOARD_TABS = {"streams", "calendar", "people"}


def _read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected object JSON in {path}")
    return payload


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
        "aliases": {
            "href": f"/portal/api/aliases?msn_id={msn_id}",
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
                "member_id": _extract_member_msn_id(record),
            }
        )
    return aliases


MSN_ID = _infer_local_msn_id()
TOOL_TABS = register_tool_blueprints(app, read_enabled_tools(PRIVATE_DIR, msn_id=MSN_ID or None))


def _ensure_runtime_dirs() -> None:
    workspace_root()
    (PRIVATE_DIR / "request_log").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "data" / "cache" / "workspaces" / "board").mkdir(parents=True, exist_ok=True)


def _normalize_board_tab(value: str) -> str:
    tab = (value or "").strip().lower()
    return tab if tab in BOARD_TABS else "streams"


def _format_ts_label(ts_unix_ms: Any) -> str:
    try:
        ts = int(ts_unix_ms)
    except Exception:
        return "unknown time"
    dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _stream_rows() -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for event in reversed(read_events("streams", limit=200)):
        if str(event.get("type") or "") != "post.create":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        rows.append(
            {
                "id": str(event.get("id") or ""),
                "author_msn_id": str(event.get("author_msn_id") or "").strip(),
                "ts_unix_ms": int(event.get("ts_unix_ms") or 0),
                "ts_label": _format_ts_label(event.get("ts_unix_ms")),
                "payload": {
                    "title": str(payload.get("title") or "").strip(),
                    "text": str(payload.get("text") or "").strip(),
                },
            }
        )
    return rows


def _calendar_rows() -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for event in read_events("calendar", limit=400):
        if str(event.get("type") or "") != "event.create":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        rows.append(
            {
                "id": str(event.get("id") or ""),
                "author_msn_id": str(event.get("author_msn_id") or "").strip(),
                "ts_unix_ms": int(event.get("ts_unix_ms") or 0),
                "ts_label": _format_ts_label(event.get("ts_unix_ms")),
                "payload": {
                    "title": str(payload.get("title") or "").strip(),
                    "start_iso": str(payload.get("start_iso") or "").strip(),
                    "end_iso": str(payload.get("end_iso") or "").strip(),
                    "location": str(payload.get("location") or "").strip(),
                    "notes": str(payload.get("notes") or "").strip(),
                },
            }
        )

    rows.sort(key=lambda row: row["payload"]["start_iso"] or "9999-99-99T99:99:99Z")
    return rows


def _append_workspace_audit(event_type: str, payload: Dict[str, Any]) -> None:
    safe_payload = dict(payload)
    safe_payload["type"] = event_type
    append_request_log_event(PRIVATE_DIR, MSN_ID or _infer_local_msn_id() or "cvcc", safe_payload)


def _board_redirect(member_msn_id: str, as_alias_id: str, tab: str, theme: str, *, status: str = "", error: str = ""):
    query: Dict[str, str] = {
        "member_msn_id": member_msn_id,
        "tab": _normalize_board_tab(tab),
    }
    if as_alias_id:
        query["as_alias_id"] = as_alias_id
    if theme:
        query["theme"] = theme
    if status:
        query["status"] = status
    if error:
        query["error"] = error
    return redirect(f"/portal/embed/board_member?{urlencode(query)}")


_ensure_runtime_dirs()


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
        return render_template("home.html", aliases=aliases, msn_id=MSN_ID, tool_tabs=TOOL_TABS)
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


@app.get("/portal/embed/board_member")
def portal_embed_board_member():
    member_msn_id = (request.args.get("member_msn_id") or "").strip()
    if not member_msn_id:
        abort(400, description="Missing required query param: member_msn_id")
    require_board_member(member_msn_id)

    as_alias_id = (request.args.get("as_alias_id") or "").strip()
    active_tab = _normalize_board_tab(request.args.get("tab") or "")
    theme = (request.args.get("theme") or "").strip()

    status_token = (request.args.get("status") or "").strip().lower()
    error_message = (request.args.get("error") or "").strip()
    status_message = ""
    status_level = "warn"
    if status_token == "post_saved":
        status_message = "Post saved to shared board stream."
        status_level = "success"
    elif status_token == "event_saved":
        status_message = "Calendar event saved to shared board calendar."
        status_level = "success"
    elif error_message:
        status_message = error_message
        status_level = "warn"

    return render_template(
        "board_member_embed_shell.html",
        member_msn_id=member_msn_id,
        as_alias_id=as_alias_id,
        active_tab=active_tab,
        streams=_stream_rows(),
        calendar_events=_calendar_rows(),
        people=materialize_people(),
        theme=theme,
        status_message=status_message,
        status_level=status_level,
    )


@app.post("/portal/embed/board_member/streams/post")
def portal_embed_board_member_streams_post():
    member_msn_id = (request.form.get("member_msn_id") or "").strip()
    as_alias_id = (request.form.get("as_alias_id") or "").strip()
    theme = (request.form.get("theme") or "").strip()
    require_board_member(member_msn_id)

    post_text = (request.form.get("post_text") or "").strip()
    post_title = (request.form.get("post_title") or "").strip()
    if not post_text:
        return _board_redirect(member_msn_id, as_alias_id, "streams", theme, error="Post text is required.")

    event_payload = {"text": post_text}
    if post_title:
        event_payload["title"] = post_title

    append_workspace_event(
        "streams",
        {
            "id": str(uuid.uuid4()),
            "ts_unix_ms": int(time.time() * 1000),
            "author_msn_id": member_msn_id,
            "type": "post.create",
            "payload": event_payload,
        },
    )
    _append_workspace_audit(
        "workspace.streams.post.created",
        {
            "member_msn_id": member_msn_id,
            "as_alias_id": as_alias_id,
            "title": post_title,
            "text_len": len(post_text),
        },
    )
    return _board_redirect(member_msn_id, as_alias_id, "streams", theme, status="post_saved")


@app.post("/portal/embed/board_member/calendar/event")
def portal_embed_board_member_calendar_event():
    member_msn_id = (request.form.get("member_msn_id") or "").strip()
    as_alias_id = (request.form.get("as_alias_id") or "").strip()
    theme = (request.form.get("theme") or "").strip()
    require_board_member(member_msn_id)

    title = (request.form.get("title") or "").strip()
    start_iso = (request.form.get("start_iso") or "").strip()
    end_iso = (request.form.get("end_iso") or "").strip()
    location = (request.form.get("location") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    if not title or not start_iso or not end_iso:
        return _board_redirect(
            member_msn_id,
            as_alias_id,
            "calendar",
            theme,
            error="title, start_iso, and end_iso are required.",
        )

    append_workspace_event(
        "calendar",
        {
            "id": str(uuid.uuid4()),
            "ts_unix_ms": int(time.time() * 1000),
            "author_msn_id": member_msn_id,
            "type": "event.create",
            "payload": {
                "title": title,
                "start_iso": start_iso,
                "end_iso": end_iso,
                "location": location,
                "notes": notes,
            },
        },
    )
    _append_workspace_audit(
        "workspace.calendar.event.created",
        {
            "member_msn_id": member_msn_id,
            "as_alias_id": as_alias_id,
            "title": title,
            "start_iso": start_iso,
            "end_iso": end_iso,
            "location": location,
        },
    )
    return _board_redirect(member_msn_id, as_alias_id, "calendar", theme, status="event_saved")


register_aliases_routes(app, private_dir=PRIVATE_DIR, options_private_fn=_options_private)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)

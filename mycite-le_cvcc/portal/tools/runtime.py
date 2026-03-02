from __future__ import annotations

import importlib
import json
import os
import re
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Iterable, List, Optional

_TOOL_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _safe_tool_id(value: str) -> str:
    token = (value or "").strip().lower()
    if not _TOOL_ID_RE.fullmatch(token):
        raise ValueError("Invalid tool identifier")
    return token


def _default_title(tool_id: str) -> str:
    return tool_id.replace("_", " ").replace("-", " ").strip().title() or tool_id


def _config_path(private_dir: Path, msn_id: Optional[str]) -> Optional[Path]:
    if msn_id:
        exact = private_dir / f"mycite-config-{msn_id}.json"
        if exact.exists() and exact.is_file():
            return exact

    env_msn = str(os.environ.get("MSN_ID") or "").strip()
    if env_msn:
        env_path = private_dir / f"mycite-config-{env_msn}.json"
        if env_path.exists() and env_path.is_file():
            return env_path

    for candidate in sorted(private_dir.glob("mycite-config-*.json")):
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def read_enabled_tools(private_dir: Path, msn_id: str | None) -> list[str]:
    path = _config_path(private_dir, msn_id)
    if path is None:
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    if not isinstance(payload, dict):
        return []

    raw = payload.get("enabled_tools")
    if not isinstance(raw, list):
        return []

    out: List[str] = []
    seen = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        try:
            tool_id = _safe_tool_id(item)
        except ValueError:
            continue
        if tool_id in seen:
            continue
        seen.add(tool_id)
        out.append(tool_id)
    return out


def load_tool_module(tool_id: str) -> ModuleType | None:
    safe = _safe_tool_id(tool_id)
    try:
        return importlib.import_module(f"portal.tools.{safe}")
    except Exception:
        return None


def resolve_tool_tab(module: ModuleType, tool_id: str) -> Dict[str, str]:
    safe_id = _safe_tool_id(str(getattr(module, "TOOL_ID", tool_id) or tool_id))

    title_raw = getattr(module, "TOOL_TITLE", "")
    title = str(title_raw).strip() if isinstance(title_raw, str) else ""
    if not title:
        title = _default_title(safe_id)

    default_home_path = f"/portal/tools/{safe_id}/home"
    home_path_raw = getattr(module, "TOOL_HOME_PATH", default_home_path)
    home_path = str(home_path_raw).strip() if isinstance(home_path_raw, str) else default_home_path
    if not home_path.startswith("/portal/"):
        home_path = default_home_path

    return {
        "tool_id": safe_id,
        "title": title,
        "home_path": home_path,
        "panel_id": f"tool-{safe_id}",
    }


def register_tool_blueprints(app: Any, enabled_tool_ids: Iterable[str]) -> list[Dict[str, str]]:
    tabs: List[Dict[str, str]] = []
    seen = set()

    for raw_tool_id in enabled_tool_ids:
        try:
            tool_id = _safe_tool_id(raw_tool_id)
        except ValueError:
            continue
        if tool_id in seen:
            continue
        seen.add(tool_id)

        module = load_tool_module(tool_id)
        if module is None:
            continue

        blueprint = getattr(module, "TOOL_BLUEPRINT", None)
        if blueprint is not None:
            try:
                app.register_blueprint(blueprint)
            except Exception:
                continue

        tabs.append(resolve_tool_tab(module, tool_id))

    return tabs

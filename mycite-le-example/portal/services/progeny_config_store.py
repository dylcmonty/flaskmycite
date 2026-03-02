from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _config_dir(config_dir: Optional[Path] = None) -> Path:
    if config_dir is not None:
        return config_dir
    return Path(__file__).resolve().parents[1] / "progeny_configs"


def _safe_name(value: str) -> str:
    name = (value or "").strip().lower()
    if not name or not _NAME_RE.fullmatch(name):
        raise ValueError("Invalid progeny config identifier")
    return name


def _read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON in {path}")
    return payload


def get_config(progeny_type: str, *, config_dir: Optional[Path] = None) -> Dict[str, Any]:
    safe = _safe_name(progeny_type)
    path = _config_dir(config_dir) / f"{safe}.json"
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"No progeny config found for type={safe}")
    payload = _read_json(path)
    payload.setdefault("progeny_type", safe)
    fields = payload.get("fields")
    if not isinstance(fields, list):
        payload["fields"] = []
    return payload


def get_client_config(client_key: str, *, config_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    raw = _safe_name(client_key)
    normalized = raw if raw.startswith("client_") else f"client_{raw}"
    try:
        return get_config(normalized, config_dir=config_dir)
    except FileNotFoundError:
        return None

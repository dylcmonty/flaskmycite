from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

RESOURCE_NAMES = {"streams", "calendar"}
BOARD_MEMBER_FILENAME_RE = re.compile(r"-progeny-(?P<member>[^/]+)-board_member\.json$", re.IGNORECASE)


def _private_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "private"


def workspace_root() -> Path:
    root = _private_dir() / "workspaces" / "board" / "v1"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cache_dir() -> Path:
    cache = Path(__file__).resolve().parents[2] / "data" / "cache" / "workspaces" / "board"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _resource_path(resource: str) -> Path:
    normalized = (resource or "").strip().lower()
    if normalized not in RESOURCE_NAMES:
        raise ValueError(f"Unknown resource: {resource}")
    return workspace_root() / f"{normalized}.ndjson"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_relaxed(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Allows configs with trailing commas while preserving strict dict expectation.
        cleaned = re.sub(r",(\s*[\]}])", r"\1", text)
        payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON in {path}")
    return payload


def append_event(resource: str, event: Dict[str, Any]) -> None:
    _cache_dir()
    path = _resource_path(resource)
    payload = dict(event or {})
    payload.setdefault("id", str(uuid.uuid4()))
    payload.setdefault("ts_unix_ms", int(time.time() * 1000))
    payload.setdefault("type", "unknown")
    payload.setdefault("author_msn_id", "")
    payload.setdefault("payload", {})
    if not isinstance(payload.get("payload"), dict):
        payload["payload"] = {}

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, separators=(",", ":")) + "\n")


def read_events(resource: str, limit: int = 200) -> List[Dict[str, Any]]:
    path = _resource_path(resource)
    if not path.exists():
        return []

    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)

    if limit > 0 and len(rows) > limit:
        return rows[-limit:]
    return rows


def _upsert_person(people: Dict[str, Dict[str, str]], msn_id: str, display_name: str, role: str) -> None:
    token = str(msn_id or "").strip()
    if not token:
        return
    if token in people:
        return
    people[token] = {
        "msn_id": token,
        "display_name": str(display_name or "").strip() or token,
        "role": str(role or "").strip() or "board_member",
    }


def _extract_member_id_from_filename(name: str) -> str:
    m = BOARD_MEMBER_FILENAME_RE.search(str(name or ""))
    if m:
        return str(m.group("member") or "").strip()
    return ""


def _people_from_board_member_files(people: Dict[str, Dict[str, str]]) -> None:
    progeny_dir = _private_dir() / "progeny"
    if not progeny_dir.exists():
        return

    for path in sorted(progeny_dir.rglob("*.json")):
        if not path.is_file():
            continue
        try:
            payload = _read_json(path)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue

        progeny_type = str(payload.get("progeny_type") or payload.get("role") or "").strip().lower()
        if progeny_type and progeny_type != "board_member":
            continue
        if not progeny_type and "board_member" not in path.name.lower():
            continue

        member_id = str(
            payload.get("member_msn_id")
            or payload.get("child_msn_id")
            or payload.get("tenant_msn_id")
            or payload.get("msn_id")
            or ""
        ).strip()
        if not member_id:
            member_id = _extract_member_id_from_filename(path.name)

        display_name = str(
            payload.get("display_name")
            or payload.get("title")
            or payload.get("name")
            or payload.get("label")
            or member_id
        ).strip()
        role = str(payload.get("role") or "board_member").strip() or "board_member"
        _upsert_person(people, member_id, display_name, role)


def _people_from_config(people: Dict[str, Dict[str, str]]) -> None:
    for cfg in sorted(_private_dir().glob("mycite-config-*.json")):
        matched = False
        try:
            payload = _read_json_relaxed(cfg)
            progeny = payload.get("progeny")
            if isinstance(progeny, list):
                for item in progeny:
                    if not isinstance(item, dict):
                        continue
                    for k, v in item.items():
                        if str(k).strip().lower() != "board_member":
                            continue
                        member_id = _extract_member_id_from_filename(str(v or ""))
                        if member_id:
                            _upsert_person(people, member_id, member_id, "board_member")
                            matched = True
        except Exception:
            pass

        if matched:
            continue

        text = cfg.read_text(encoding="utf-8")
        for member_id in re.findall(r"progeny-([^\"/]+)-board_member\.json", text):
            _upsert_person(people, member_id, member_id, "board_member")


def _people_from_seed_file(people: Dict[str, Dict[str, str]]) -> None:
    path = workspace_root() / "people.json"
    if not path.exists():
        return
    try:
        payload = _read_json(path)
    except Exception:
        return
    if not isinstance(payload, list):
        return
    for item in payload:
        if not isinstance(item, dict):
            continue
        _upsert_person(
            people,
            str(item.get("msn_id") or "").strip(),
            str(item.get("display_name") or "").strip(),
            str(item.get("role") or "board_member").strip() or "board_member",
        )


def materialize_people() -> List[Dict[str, str]]:
    people: Dict[str, Dict[str, str]] = {}
    _people_from_board_member_files(people)
    _people_from_config(people)
    _people_from_seed_file(people)
    return sorted(people.values(), key=lambda row: (row.get("display_name") or row.get("msn_id") or "").lower())


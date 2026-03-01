from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional


def _cache_dir(data_dir: Path) -> Path:
    return data_dir / "cache" / "contacts"


def _cache_path(data_dir: Path, sender_msn_id: str) -> Path:
    return _cache_dir(data_dir) / f"{sender_msn_id}.json"


def get_cached(data_dir: Path, sender_msn_id: str) -> Optional[Dict[str, Any]]:
    p = _cache_path(data_dir, sender_msn_id)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def put_cached(data_dir: Path, sender_msn_id: str, contact_card_dict: Dict[str, Any]) -> Path:
    payload = dict(contact_card_dict)
    payload["cached_unix_ms"] = int(time.time() * 1000)

    p = _cache_path(data_dir, sender_msn_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return p


def is_stale(contact_card_dict: Dict[str, Any], ttl_seconds: int) -> bool:
    cached_unix_ms = contact_card_dict.get("cached_unix_ms")
    if not isinstance(cached_unix_ms, int):
        return True
    age_ms = int(time.time() * 1000) - cached_unix_ms
    return age_ms > int(ttl_seconds * 1000)


def resolve(
    data_dir: Path,
    sender_msn_id: str,
    fetch_fn: Callable[[str], Dict[str, Any]],
    *,
    ttl_seconds: int = 300,
) -> Dict[str, Any]:
    cached = get_cached(data_dir, sender_msn_id)
    if cached is not None and not is_stale(cached, ttl_seconds):
        return cached

    card = fetch_fn(sender_msn_id)
    put_cached(data_dir, sender_msn_id, card)
    cached_card = get_cached(data_dir, sender_msn_id)
    return cached_card if cached_card is not None else card

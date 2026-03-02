from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

FORBIDDEN_SECRET_KEYS = {
    "private_key", "private_key_pem", "secret", "token", "password",
    "symmetric_key", "hmac_key", "hmac_key_b64", "api_key",
}


@dataclass(frozen=True)
class ReadResult:
    events: List[Dict[str, Any]]
    parse_errors: int
    total_lines: int


def _log_dir(private_dir: Path) -> Path:
    return private_dir / "request_log"


def _log_path(private_dir: Path, msn_id: str) -> Path:
    # Append-only NDJSON is the simplest durable log for this stage.
    return _log_dir(private_dir) / f"{msn_id}.ndjson"


def append_event(private_dir: Path, msn_id: str, event: Dict[str, Any]) -> Path:
    """Append a single event to the request log (NDJSON).

    - Does NOT store secrets.
    - Adds a timestamp if none exists.
    """
    d = _log_dir(private_dir)
    d.mkdir(parents=True, exist_ok=True)

    e = dict(event)
    bad = set(e.keys()).intersection(FORBIDDEN_SECRET_KEYS)
    if bad:
        raise ValueError(f"Do not store secrets in request_log. Forbidden keys: {sorted(bad)}")
    e.setdefault("ts_unix_ms", int(time.time() * 1000))
    e.setdefault("msn_id", msn_id)

    p = _log_path(private_dir, msn_id)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(e, separators=(",", ":")) + "\n")
    return p


def read_events(
    private_dir: Path,
    msn_id: str,
    *,
    limit: int = 100,
    offset: int = 0,
    reverse: bool = True,
) -> ReadResult:
    """Read events from the request log.

    Behavior:
    - If log doesn't exist: returns empty list.
    - reverse=True returns newest-first (requires loading lines; acceptable for prototype).
    """
    p = _log_path(private_dir, msn_id)
    if not p.exists():
        return ReadResult(events=[], parse_errors=0, total_lines=0)

    lines = p.read_text(encoding="utf-8").splitlines()
    total = len(lines)
    parse_errors = 0
    events: List[Dict[str, Any]] = []

    iterable = reversed(lines) if reverse else lines
    # Apply offset/limit after ordering
    sliced = list(iterable)[offset : offset + limit]

    for ln in sliced:
        if not ln.strip():
            continue
        try:
            obj = json.loads(ln)
            if isinstance(obj, dict):
                events.append(obj)
            else:
                parse_errors += 1
        except Exception:
            parse_errors += 1

    return ReadResult(events=events, parse_errors=parse_errors, total_lines=total)

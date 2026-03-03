from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_ALLOWED_ACTIONS = {"nav", "inv", "med", "man"}


@dataclass
class ParsedDirective:
    action: str
    subject: str
    method: str
    args: dict[str, Any]
    errors: list[str]
    warnings: list[str]


def _parse_compact(directive_text: str) -> tuple[str, str, str]:
    raw = str(directive_text or "").strip()
    if not raw:
        return "", "", ""

    action = ""
    subject = ""
    method = ""

    left = raw
    if ":" in raw:
        action, left = raw.split(":", 1)
    if ";" in left:
        subject, method = left.split(";", 1)
    else:
        subject = left

    return action.strip().lower(), subject.strip(), method.strip()


def parse_directive(payload: dict[str, Any] | str) -> ParsedDirective:
    errors: list[str] = []
    warnings: list[str] = []

    body: dict[str, Any]
    if isinstance(payload, str):
        body = {"directive": payload}
    elif isinstance(payload, dict):
        body = payload
    else:
        body = {}
        errors.append("Directive payload must be an object or string.")

    action = str(body.get("action") or "").strip().lower()
    subject = str(body.get("subject") or "").strip()
    method = str(body.get("method") or "").strip()
    args = body.get("args") if isinstance(body.get("args"), dict) else {}

    compact = str(body.get("directive") or "").strip()
    if compact and not action:
        compact_action, compact_subject, compact_method = _parse_compact(compact)
        action = action or compact_action
        subject = subject or compact_subject
        method = method or compact_method

    if action not in _ALLOWED_ACTIONS:
        errors.append("action must be one of: nav, inv, med, man")

    return ParsedDirective(
        action=action,
        subject=subject,
        method=method,
        args=dict(args),
        errors=errors,
        warnings=warnings,
    )

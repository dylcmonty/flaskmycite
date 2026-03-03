from __future__ import annotations

from typing import Any


def empty_pane(kind: str = "empty") -> dict[str, Any]:
    return {"kind": kind, "payload": {}}


def pane(kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"kind": str(kind or "empty"), "payload": dict(payload or {})}


def response_payload(
    *,
    state: dict[str, Any],
    left_pane_vm: dict[str, Any],
    right_pane_vm: dict[str, Any],
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
    staged_edits: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "state": state,
        "left_pane_vm": left_pane_vm,
        "right_pane_vm": right_pane_vm,
        "errors": list(errors or []),
        "warnings": list(warnings or []),
        "staged_edits": list(staged_edits or []),
    }

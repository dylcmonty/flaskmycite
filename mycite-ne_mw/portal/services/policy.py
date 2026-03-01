from __future__ import annotations

import re

_PUBLIC_CONTACT_CARD_RE = re.compile(r"^/[^/]+\.json$")


def is_public_path(path: str) -> bool:
    """Return True for anonymous public endpoints.

    Public HTTP is intentionally limited to GET /<msn_id>.json (plus OPTIONS).
    """
    if path.startswith("/portal/") or path.startswith("/api/"):
        return False
    return _PUBLIC_CONTACT_CARD_RE.fullmatch(path) is not None


def is_portal_path(path: str) -> bool:
    """Return True for portal UI and portal-only APIs."""
    return path == "/portal" or path.startswith("/portal/")


def is_external_signed_path(path: str) -> bool:
    """Return True for externally callable signed endpoints."""
    return path.startswith("/api/")

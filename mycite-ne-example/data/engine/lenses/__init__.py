from __future__ import annotations

from typing import Any

from data.engine.lenses.ascii import AsciiLens
from data.engine.lenses.base import Lens
from data.engine.lenses.default import DefaultLens


LENS_REGISTRY: dict[str, Lens] = {
    "default": DefaultLens(),
    "ascii": AsciiLens(),
}


def get_lens(field_id: str, config: dict[str, Any] | None = None) -> Lens:
    cfg = config or {}
    field_lenses = cfg.get("field_lenses") if isinstance(cfg.get("field_lenses"), dict) else {}
    configured = str(field_lenses.get(field_id) or "default").strip().lower()
    return LENS_REGISTRY.get(configured, LENS_REGISTRY["default"])

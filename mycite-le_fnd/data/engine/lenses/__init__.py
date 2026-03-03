from __future__ import annotations

from typing import Any

from data.engine.lenses.ascii import AsciiLens
from data.engine.lenses.base import Lens, LensResult
from data.engine.lenses.default import DefaultLens


LENS_REGISTRY: dict[str, Lens] = {
    "default": DefaultLens(),
    "ascii": AsciiLens(),
}


def _dev_lenses(config: dict[str, Any]) -> dict[str, Lens]:
    if not bool(config.get("enable_dev_data_features")):
        return {}

    try:
        from data.dev.lenses.experimental_ascii_plus import validate as experimental_validate
    except Exception:
        return {}

    class _ExperimentalAsciiPlusLens:
        lens_id = "experimental_ascii_plus"

        def validate(self, display_value: str) -> LensResult:
            result = experimental_validate(str(display_value or ""))
            return LensResult(
                ok=bool(result.get("ok")),
                errors=list(result.get("errors") or []),
                warnings=list(result.get("warnings") or []),
            )

        def encode(self, display_value: str) -> str:
            return str(display_value or "")

        def decode(self, raw_value: str) -> str:
            return str(raw_value or "")

        def render(self, display_value: str) -> str:
            return str(display_value or "")

    return {"experimental_ascii_plus": _ExperimentalAsciiPlusLens()}


def get_lens(field_id: str, lens_context: dict[str, Any] | None = None, config: dict[str, Any] | None = None) -> Lens:
    context = lens_context or {}
    cfg = config or {}

    registry: dict[str, Lens] = dict(LENS_REGISTRY)
    registry.update(_dev_lenses(cfg))

    overrides = context.get("overrides") if isinstance(context.get("overrides"), dict) else {}
    configured_map = cfg.get("field_lenses") if isinstance(cfg.get("field_lenses"), dict) else {}

    lens_id = ""
    if field_id in overrides:
        lens_id = str(overrides.get(field_id) or "").strip().lower()
    elif field_id in configured_map:
        lens_id = str(configured_map.get(field_id) or "").strip().lower()
    else:
        lens_id = str(context.get("default") or cfg.get("default_lens") or "default").strip().lower()

    return registry.get(lens_id, registry["default"])

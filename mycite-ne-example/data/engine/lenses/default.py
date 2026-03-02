from __future__ import annotations

from data.engine.lenses.base import LensResult


class DefaultLens:
    lens_id = "default"

    def validate(self, display_value: str) -> LensResult:
        return LensResult(ok=True, errors=[], warnings=[])

    def encode(self, display_value: str) -> str:
        return str(display_value or "")

    def decode(self, raw_value: str) -> str:
        return str(raw_value or "")

    def render(self, display_value: str) -> str:
        return str(display_value or "")

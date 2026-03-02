from __future__ import annotations

from data.engine.lenses.base import LensResult


class AsciiLens:
    lens_id = "ascii"

    def validate(self, display_value: str) -> LensResult:
        value = str(display_value or "")
        if all(ord(ch) < 128 for ch in value):
            return LensResult(ok=True, errors=[], warnings=[])
        return LensResult(ok=False, errors=["Non-ASCII characters are not allowed by ascii lens."], warnings=[])

    def encode(self, display_value: str) -> str:
        # TODO: plug in pattern-recognition normalization for structured tokens.
        return str(display_value or "")

    def decode(self, raw_value: str) -> str:
        return str(raw_value or "")

    def render(self, display_value: str) -> str:
        return str(display_value or "")

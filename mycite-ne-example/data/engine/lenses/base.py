from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class LensResult:
    ok: bool
    errors: list[str]
    warnings: list[str]


class Lens(Protocol):
    lens_id: str

    def validate(self, display_value: str) -> LensResult:
        ...

    def encode(self, display_value: str) -> str:
        ...

    def decode(self, raw_value: str) -> str:
        ...

    def render(self, display_value: str) -> str:
        ...

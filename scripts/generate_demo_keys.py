#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> Dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def _public_cards() -> List[Path]:
    cards: List[Path] = []
    for portal_dir in sorted(ROOT.glob("mycite-*")):
        if not portal_dir.is_dir():
            continue
        public_dir = portal_dir / "public"
        if not public_dir.exists():
            continue
        cards.extend(sorted(public_dir.glob("*.json")))
    return cards


def _ensure_private_key(portal_dir: Path, msn_id: str) -> Path:
    key_path = portal_dir / "vault" / "keys" / f"{msn_id}_private.pem"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        return key_path

    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path.write_bytes(private_bytes)
    return key_path


def _public_pem_from_private(private_key_path: Path) -> str:
    private_key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    public_key = private_key.public_key()
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")


def main() -> int:
    changed = 0
    inspected = 0
    for card_path in _public_cards():
        inspected += 1
        portal_dir = card_path.parents[1]
        payload = _load_json(card_path)
        msn_id = str(payload.get("msn_id") or "").strip()
        if not msn_id:
            print(f"skip {card_path}: missing msn_id")
            continue

        private_key_path = _ensure_private_key(portal_dir, msn_id)
        public_pem = _public_pem_from_private(private_key_path)

        if payload.get("public_key") != public_pem:
            payload["public_key"] = public_pem
            card_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            changed += 1
            print(f"updated {card_path}")
        else:
            print(f"ok {card_path}")

    print(f"inspected={inspected} changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

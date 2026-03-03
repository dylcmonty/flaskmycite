from __future__ import annotations

import json
from pathlib import Path
from typing import Any


TABLE_SPECS: dict[str, dict[str, str]] = {
    "anthology": {"filename": "demo-anthology.json", "title": "Anthology"},
    "conspectus": {"filename": "demo-conspectus.json", "title": "Conspectus"},
    "samras": {"filename": "demo-SAMRAS_MSN.json", "title": "SAMRAS"},
}

PRESENTATION_SCHEMA = "mycite.presentation.datum_icons.v0"


class JsonStorageBackend:
    """JSON-backed adapter for anthology/conspectus/SAMRAS payloads and presentation sidecars."""

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)

    def known_tables(self) -> list[str]:
        return list(TABLE_SPECS.keys())

    def table_title(self, table_id: str) -> str:
        spec = TABLE_SPECS.get(str(table_id or "").strip().lower(), {})
        return str(spec.get("title") or table_id)

    def _table_path(self, table_id: str) -> Path:
        token = str(table_id or "").strip().lower()
        spec = TABLE_SPECS.get(token)
        if not spec:
            raise ValueError(f"Unknown table_id: {table_id}")
        return self.data_dir / str(spec["filename"])

    def presentation_path(self) -> Path:
        return self.data_dir / "presentation" / "datum_icons.json"

    def read_payload(self, table_id: str) -> dict[str, Any]:
        path = self._table_path(table_id)
        if not path.exists() or not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def write_payload(self, table_id: str, payload: dict[str, Any]) -> None:
        path = self._table_path(table_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def load_all_rows(self) -> dict[str, list[dict[str, str]]]:
        return {table_id: self.load_rows(table_id) for table_id in self.known_tables()}

    def load_rows(self, table_id: str) -> list[dict[str, str]]:
        token = str(table_id or "").strip().lower()
        payload = self.read_payload(token)
        if token == "anthology":
            return self._anthology_rows(payload)
        if token == "conspectus":
            return self._conspectus_rows(payload)
        if token == "samras":
            return self._samras_rows(payload)
        return []

    def persist_rows(self, table_id: str, rows: list[dict[str, str]]) -> dict[str, Any]:
        token = str(table_id or "").strip().lower()
        try:
            if token == "anthology":
                payload = self._rows_to_anthology(rows)
            elif token == "conspectus":
                payload = self._rows_to_conspectus(rows)
            elif token == "samras":
                payload = self._rows_to_samras(rows)
            else:
                return {"ok": False, "errors": [f"Unknown table_id: {table_id}"], "warnings": []}
            self.write_payload(token, payload)
            return {"ok": True, "errors": [], "warnings": []}
        except Exception as exc:
            return {"ok": False, "errors": [str(exc)], "warnings": []}

    def load_datum_icons_map(self) -> dict[str, str]:
        path = self.presentation_path()
        if not path.exists() or not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        mapping = payload.get("map") if isinstance(payload.get("map"), dict) else {}

        out: dict[str, str] = {}
        for key, value in mapping.items():
            datum_id = str(key or "").strip()
            rel = self._normalize_icon_relpath(value)
            if datum_id and rel:
                out[datum_id] = rel
        return out

    def persist_datum_icons_map(self, mapping: dict[str, str]) -> dict[str, Any]:
        path = self.presentation_path()
        try:
            existing_meta: dict[str, Any] = {}
            if path.exists() and path.is_file():
                current = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(current, dict) and isinstance(current.get("_meta"), dict):
                    existing_meta = dict(current.get("_meta") or {})

            payload = {
                "_meta": {
                    "schema": str(existing_meta.get("schema") or PRESENTATION_SCHEMA),
                    "icon_root": str(existing_meta.get("icon_root") or "assets/icons"),
                },
                "map": {},
            }

            cleaned: dict[str, str] = {}
            for key, value in dict(mapping or {}).items():
                datum_id = str(key or "").strip()
                rel = self._normalize_icon_relpath(value)
                if datum_id and rel:
                    cleaned[datum_id] = rel
            payload["map"] = cleaned

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            return {"ok": True, "errors": [], "warnings": []}
        except Exception as exc:
            return {"ok": False, "errors": [str(exc)], "warnings": []}

    @staticmethod
    def _as_text(value: object) -> str:
        return "" if value is None else str(value)

    @staticmethod
    def _normalize_icon_relpath(value: object) -> str:
        token = str(value or "").strip().replace("\\", "/")
        token = token.lstrip("/")
        if token.startswith("assets/icons/"):
            token = token[len("assets/icons/") :]
        if token.startswith("/"):
            token = token[1:]
        return token

    def _anthology_rows(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for key, value in payload.items():
            row_values = value if isinstance(value, list) else []
            base = row_values[0] if len(row_values) > 0 and isinstance(row_values[0], list) else []
            labels = row_values[1] if len(row_values) > 1 and isinstance(row_values[1], list) else []
            rows.append(
                {
                    "row_id": self._as_text(key),
                    "identifier": self._as_text(base[0] if len(base) > 0 else key),
                    "reference": self._as_text(base[1] if len(base) > 1 else ""),
                    "magnitude": self._as_text(base[2] if len(base) > 2 else ""),
                    "label": self._as_text(labels[0] if len(labels) > 0 else ""),
                    "_source": "anthology",
                }
            )
        return rows

    def _conspectus_rows(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for key, value in payload.items():
            refs = value if isinstance(value, list) else [value]
            rows.append(
                {
                    "row_id": self._as_text(key),
                    "identifier": self._as_text(key),
                    "references": ", ".join(self._as_text(item) for item in refs),
                    "_source": "conspectus",
                }
            )
        return rows

    def _samras_rows(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for key, value in payload.items():
            names = value if isinstance(value, list) else [value]
            rows.append(
                {
                    "row_id": self._as_text(key),
                    "msn_id": self._as_text(key),
                    "name": self._as_text(names[0] if names else ""),
                    "_source": "samras",
                }
            )
        return rows

    def _rows_to_anthology(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for index, row in enumerate(rows):
            key = str(row.get("row_id") or row.get("identifier") or f"row-{index + 1}").strip()
            if not key:
                continue
            out[key] = [
                [
                    self._as_text(row.get("identifier")),
                    self._as_text(row.get("reference")),
                    self._as_text(row.get("magnitude")),
                ],
                [self._as_text(row.get("label"))],
            ]
        return out

    def _rows_to_conspectus(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for index, row in enumerate(rows):
            key = str(row.get("row_id") or row.get("identifier") or f"row-{index + 1}").strip()
            if not key:
                continue
            refs_text = self._as_text(row.get("references"))
            refs = [part.strip() for part in refs_text.split(",") if part.strip()]
            out[key] = refs
        return out

    def _rows_to_samras(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for index, row in enumerate(rows):
            key = str(row.get("row_id") or row.get("msn_id") or f"row-{index + 1}").strip()
            if not key:
                continue
            out[key] = [self._as_text(row.get("name"))]
        return out

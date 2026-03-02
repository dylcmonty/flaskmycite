from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


TABLE_SPECS: dict[str, dict[str, str]] = {
    "anthology": {"filename": "demo-anthology.json", "title": "Anthology"},
    "conspectus": {"filename": "demo-conspectus.json", "title": "Conspectus"},
    "samras": {"filename": "demo-SAMRAS_MSN.json", "title": "SAMRAS"},
}


class JsonStorageBackend:
    """JSON-only storage backend for portal data tables."""

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)

    def known_tables(self) -> list[str]:
        return list(TABLE_SPECS.keys())

    def table_title(self, table_id: str) -> str:
        spec = TABLE_SPECS.get(table_id, {})
        return str(spec.get("title") or table_id)

    def _table_path(self, table_id: str) -> Path:
        spec = TABLE_SPECS.get(table_id)
        if not spec:
            raise ValueError(f"Unknown table_id: {table_id}")
        return self.data_dir / str(spec["filename"])

    def read_payload(self, table_id: str) -> dict[str, Any]:
        path = self._table_path(table_id)
        if not path.exists() or not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        return payload

    def write_payload(self, table_id: str, payload: dict[str, Any]) -> None:
        path = self._table_path(table_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def load_rows(self, table_id: str) -> list[dict[str, str]]:
        payload = self.read_payload(table_id)
        if table_id == "anthology":
            return self._anthology_rows(payload)
        if table_id == "conspectus":
            return self._conspectus_rows(payload)
        if table_id == "samras":
            return self._samras_rows(payload)
        return []

    def load_all_rows(self) -> dict[str, list[dict[str, str]]]:
        return {table_id: self.load_rows(table_id) for table_id in self.known_tables()}

    def persist_rows(self, table_id: str, rows: list[dict[str, str]]) -> dict[str, Any]:
        errors: list[str] = []
        try:
            if table_id == "anthology":
                payload = self._rows_to_anthology(rows)
            elif table_id == "conspectus":
                payload = self._rows_to_conspectus(rows)
            elif table_id == "samras":
                payload = self._rows_to_samras(rows)
            else:
                return {"ok": False, "errors": [f"Unknown table_id: {table_id}"], "warnings": []}
            self.write_payload(table_id, payload)
        except Exception as exc:
            errors.append(str(exc))
        return {"ok": not errors, "errors": errors, "warnings": []}

    @staticmethod
    def _as_text(value: object) -> str:
        if value is None:
            return ""
        return str(value)

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
            refs = [token.strip() for token in refs_text.split(",") if token.strip()]
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

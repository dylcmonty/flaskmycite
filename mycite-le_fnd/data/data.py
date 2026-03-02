from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from flask import abort, jsonify, render_template, request

TABLE_SPECS: dict[str, dict[str, object]] = {
    "anthology": {
        "filename": "demo-anthology.json",
        "label": "Anthology",
        "columns": ["identifier", "reference", "magnitude", "label"],
    },
    "conspectus": {
        "filename": "demo-conspectus.json",
        "label": "Conspectus",
        "columns": ["identifier", "references"],
    },
    "samras": {
        "filename": "demo-SAMRAS_MSN.json",
        "label": "SAMRAS",
        "columns": ["msn_id", "name"],
    },
}


def list_table_catalog() -> list[dict[str, str]]:
    return [
        {
            "table_name": table_name,
            "label": str(spec["label"]),
            "href": f"/portal/data/{table_name}",
        }
        for table_name, spec in TABLE_SPECS.items()
    ]


def _data_file_path(filename: str) -> Path:
    # Keep all storage access in this module so DB migration only touches this layer.
    return Path(__file__).resolve().parents[1] / "data" / filename


def _read_table_payload(table_name: str) -> dict:
    spec = TABLE_SPECS.get(table_name)
    if not spec:
        raise FileNotFoundError(f"Unknown table: {table_name}")

    filename = str(spec["filename"])
    data_path = _data_file_path(filename)
    if not data_path.exists() or not data_path.is_file():
        raise FileNotFoundError(f"Data file does not exist: {data_path}")

    payload = json.loads(data_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {data_path}")
    return payload


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _transform_anthology(payload: dict) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key, value in payload.items():
        row_values = value if isinstance(value, list) else []
        base = row_values[0] if len(row_values) > 0 and isinstance(row_values[0], list) else []
        labels = row_values[1] if len(row_values) > 1 and isinstance(row_values[1], list) else []

        identifier = _as_text(base[0] if len(base) > 0 else key)
        reference = _as_text(base[1] if len(base) > 1 else "")
        magnitude = _as_text(base[2] if len(base) > 2 else "")
        label = _as_text(labels[0] if len(labels) > 0 else "")

        rows.append(
            {
                "identifier": identifier,
                "reference": reference,
                "magnitude": magnitude,
                "label": label,
            }
        )
    return rows


def _transform_conspectus(payload: dict) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key, value in payload.items():
        refs = value if isinstance(value, list) else [value]
        rows.append(
            {
                "identifier": _as_text(key),
                "references": ", ".join(_as_text(item) for item in refs),
            }
        )
    return rows


def _transform_samras(payload: dict) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key, value in payload.items():
        names = value if isinstance(value, list) else [value]
        rows.append(
            {
                "msn_id": _as_text(key),
                "name": _as_text(names[0] if names else ""),
            }
        )
    return rows


def load_table(table_name: str) -> list[dict[str, str]]:
    normalized = (table_name or "").strip().lower()
    payload = _read_table_payload(normalized)

    if normalized == "anthology":
        return _transform_anthology(payload)
    if normalized == "conspectus":
        return _transform_conspectus(payload)
    if normalized == "samras":
        return _transform_samras(payload)

    raise FileNotFoundError(f"Unknown table: {table_name}")


def register_data_routes(
    app,
    *,
    aliases_provider: Callable[[], list[dict]] | None = None,
) -> None:
    def _aliases() -> list[dict]:
        if aliases_provider is None:
            return []
        return aliases_provider()

    @app.get("/portal/data")
    def portal_data_home():
        return render_template("data_home.html", aliases=_aliases(), tables=list_table_catalog())

    @app.get("/portal/data/<table_name>")
    def portal_data_table(table_name: str):
        normalized = (table_name or "").strip().lower()
        spec = TABLE_SPECS.get(normalized)
        if not spec:
            abort(404, description=f"Unknown table: {table_name}")

        try:
            rows = load_table(normalized)
        except FileNotFoundError:
            abort(404, description=f"No data table found for name={table_name}")

        columns = list(rows[0].keys()) if rows else list(spec.get("columns", []))
        return render_template(
            "data_table.html",
            aliases=_aliases(),
            table_name=normalized,
            table_label=str(spec["label"]),
            rows=rows,
            columns=columns,
        )

    @app.post("/portal/data/<table_name>/update")
    def portal_data_update(table_name: str):
        normalized = (table_name or "").strip().lower()
        if normalized not in TABLE_SPECS:
            abort(404, description=f"Unknown table: {table_name}")

        submitted = {key: value for key, value in request.form.items()}
        # TODO: Persist updates through a storage adapter (DB-backed, no direct file writes).
        # TODO: Add pattern recognition for known value shapes and auto-normalization hints.
        # TODO: Add reference chain categorization support for table relationships.
        return (
            jsonify(
                {
                    "ok": False,
                    "message": "Not implemented",
                    "table_name": normalized,
                    "submitted": submitted,
                }
            ),
            501,
        )

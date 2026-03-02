from __future__ import annotations

import hashlib
from typing import Any

from data.engine.graph import DatumGraph


META_FIELDS = {"row_id", "_source", "_node_id"}


def row_signature(row: dict[str, Any]) -> frozenset[str]:
    return frozenset(
        key
        for key, value in row.items()
        if key not in META_FIELDS and str(value or "").strip()
    )


def _signature_id(signature: frozenset[str]) -> str:
    token = "|".join(sorted(signature))
    if not token:
        return "sig-empty"
    digest = hashlib.sha1(token.encode("utf-8")).hexdigest()[:12]
    return f"sig-{digest}"


def cluster_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        signature = row_signature(row)
        instance_id = _signature_id(signature)
        bucket = grouped.setdefault(
            instance_id,
            {
                "instance_id": instance_id,
                "signature": sorted(signature),
                "rows": [],
            },
        )
        bucket["rows"].append(row)

    out = list(grouped.values())
    out.sort(key=lambda item: item["instance_id"])
    return out


def infer_tables(graph: DatumGraph, rows_by_table: dict[str, list[dict[str, str]]], title_by_table: dict[str, str]) -> dict[str, dict[str, Any]]:
    inferred: dict[str, dict[str, Any]] = {}

    for node in graph.nodes.values():
        title_token = (str(node.label or "") or str(node.identifier or "")).lower()
        if node.value_group != 0 or "table" not in title_token:
            continue
        if node.layer is None:
            continue

        table_id = f"layer-{node.layer}"
        rows: list[dict[str, str]] = []
        for candidate_id in graph.find_by_layer(node.layer):
            candidate = graph.get_node(candidate_id)
            if not candidate or candidate.node_id == node.node_id:
                continue
            if candidate.value_group == 0:
                continue
            rows.append(dict(candidate.raw))

        inferred[table_id] = {
            "table_id": table_id,
            "title": str(node.label or node.identifier or table_id),
            "layer": node.layer,
            "archetype_id": node.node_id,
            "rows": rows,
        }

    if inferred:
        return inferred

    for table_id, rows in rows_by_table.items():
        if not rows:
            continue
        first_identifier = str(rows[0].get("identifier") or "").strip()
        layer = None
        if first_identifier:
            try:
                layer = int(first_identifier.split("-")[0])
            except Exception:
                layer = None
        inferred[table_id] = {
            "table_id": table_id,
            "title": str(title_by_table.get(table_id) or table_id),
            "layer": layer,
            "archetype_id": "",
            "rows": [dict(row) for row in rows],
        }

    return inferred

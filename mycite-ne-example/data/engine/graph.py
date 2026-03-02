from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


META_FIELDS = {"row_id", "_source", "_node_id"}


@dataclass(frozen=True)
class DatumNode:
    node_id: str
    table_id: str
    source: str
    row_id: str
    identifier: str
    label: str
    reference: str
    magnitude: str
    layer: Optional[int]
    value_group: Optional[int]
    iteration: Optional[int]
    field_ids: frozenset[str]
    raw: dict[str, str]


@dataclass
class DatumGraph:
    nodes: Dict[str, DatumNode] = field(default_factory=dict)
    by_source: Dict[str, list[str]] = field(default_factory=dict)
    by_layer: Dict[int, list[str]] = field(default_factory=dict)
    by_identifier: Dict[str, list[str]] = field(default_factory=dict)

    def get_node(self, node_id: str) -> Optional[DatumNode]:
        return self.nodes.get(node_id)

    def find_by_source(self, source: str) -> list[str]:
        return list(self.by_source.get(source, []))

    def find_by_layer(self, layer: Optional[int]) -> list[str]:
        if layer is None:
            return []
        return list(self.by_layer.get(layer, []))

    def find_by_identifier(self, identifier: str) -> list[str]:
        return list(self.by_identifier.get(identifier, []))


def parse_identifier_token(identifier: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
    token = str(identifier or "").strip()
    if not token:
        return None, None, None

    parts = token.split("-")
    if len(parts) < 3:
        return None, None, None

    layer: Optional[int] = None
    value_group: Optional[int] = None
    iteration: Optional[int] = None

    try:
        layer = int(parts[0])
    except Exception:
        layer = None

    try:
        value_group = int(parts[1])
    except Exception:
        value_group = None

    try:
        iteration = int(parts[-1])
    except Exception:
        iteration = None

    return layer, value_group, iteration


def _field_ids(row: dict[str, str]) -> frozenset[str]:
    out = {
        key
        for key, value in row.items()
        if key not in META_FIELDS and str(value or "").strip()
    }
    return frozenset(out)


def build_graph(rows_by_table: dict[str, list[dict[str, str]]]) -> DatumGraph:
    graph = DatumGraph()

    for table_id, rows in rows_by_table.items():
        for row in rows:
            row_id = str(row.get("row_id") or "").strip()
            if not row_id:
                continue

            source = str(row.get("_source") or table_id).strip() or table_id
            identifier = str(row.get("identifier") or row.get("msn_id") or row_id).strip()
            label = str(row.get("label") or row.get("name") or identifier).strip()
            reference = str(row.get("reference") or "").strip()
            magnitude = str(row.get("magnitude") or "").strip()
            layer, value_group, iteration = parse_identifier_token(identifier)

            node_id = f"{table_id}:{row_id}"
            payload = dict(row)
            payload["_node_id"] = node_id
            node = DatumNode(
                node_id=node_id,
                table_id=table_id,
                source=source,
                row_id=row_id,
                identifier=identifier,
                label=label,
                reference=reference,
                magnitude=magnitude,
                layer=layer,
                value_group=value_group,
                iteration=iteration,
                field_ids=_field_ids(payload),
                raw=payload,
            )

            graph.nodes[node_id] = node
            graph.by_source.setdefault(source, []).append(node_id)
            if layer is not None:
                graph.by_layer.setdefault(layer, []).append(node_id)
            if identifier:
                graph.by_identifier.setdefault(identifier, []).append(node_id)

    return graph

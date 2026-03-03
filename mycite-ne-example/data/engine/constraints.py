from __future__ import annotations

from typing import Any

from data.engine.graph import DatumGraph, DatumNode


def _resolve_node(graph: DatumGraph, subject: str) -> DatumNode | None:
    token = str(subject or "").strip()
    if not token:
        return None

    direct = graph.get_node(token)
    if direct is not None:
        return direct

    matches = graph.find_by_identifier(token)
    if not matches:
        return None
    return graph.get_node(matches[0])


def resolve_chain(graph: DatumGraph, subject: str, depth_limit: int = 12) -> list[dict[str, Any]]:
    node = _resolve_node(graph, subject)
    if node is None:
        return []

    chain: list[dict[str, Any]] = []
    visited: set[str] = set()
    cursor: DatumNode | None = node

    while cursor is not None and cursor.node_id not in visited and len(chain) < depth_limit:
        visited.add(cursor.node_id)
        chain.append(
            {
                "node_id": cursor.node_id,
                "identifier": cursor.identifier,
                "label": cursor.label,
                "reference": cursor.reference,
                "layer": cursor.layer,
                "value_group": cursor.value_group,
            }
        )

        ref = str(cursor.reference or "").strip()
        if not ref:
            break

        targets = graph.find_by_identifier(ref)
        if not targets:
            break

        next_node_id = targets[0]
        cursor = graph.get_node(next_node_id)

    return chain


def compile_constraint(node: DatumNode, chain: list[dict[str, Any]]) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []

    if str(node.reference or "").strip() and len(chain) <= 1:
        warnings.append("unresolved_reference")

    if node.value_group is None:
        warnings.append("identifier_not_structured")

    if node.layer is None:
        warnings.append("unknown_layer")

    return {
        "node_id": node.node_id,
        "identifier": node.identifier,
        "chain_depth": len(chain),
        "errors": errors,
        "warnings": warnings,
    }

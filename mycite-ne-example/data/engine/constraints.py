from __future__ import annotations

from typing import Any

from data.engine.graph import DatumGraph


def resolve_chain(graph: DatumGraph, datum_id: str) -> list[str]:
    node = graph.get_node(datum_id)
    if not node:
        return []

    chain: list[str] = [node.node_id]
    reference = str(node.reference or "").strip()
    if not reference:
        return chain

    matches = graph.find_by_identifier(reference)
    for match in matches:
        if match != node.node_id:
            chain.append(match)
            break

    return chain


def compile_constraint(node: Any, chain: list[str]) -> dict[str, Any]:
    warnings: list[str] = []

    reference = str(getattr(node, "reference", "") or "").strip()
    if reference and len(chain) <= 1:
        warnings.append("unresolved_reference")

    value_group = getattr(node, "value_group", None)
    if value_group is None:
        warnings.append("identifier_not_structured")

    return {
        "node_id": str(getattr(node, "node_id", "")),
        "chain": list(chain),
        "warnings": warnings,
    }

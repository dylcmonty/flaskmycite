from __future__ import annotations

from collections import defaultdict
from typing import Any

from data.engine.constraints import compile_constraint, resolve_chain
from data.engine.graph import META_FIELDS, build_graph
from data.engine.lenses import get_lens
from data.engine.tables import cluster_rows, infer_tables


class Workspace:
    def __init__(self, storage_backend, config: dict[str, Any] | None = None):
        self.storage = storage_backend
        self.config = config or {}
        self._staged: dict[tuple[str, str, str], str] = {}
        self._rows_by_table: dict[str, list[dict[str, str]]] = {}
        self._tables: dict[str, dict[str, Any]] = {}
        self._graph = build_graph({})
        self._reload()

    def _reload(self) -> None:
        self._rows_by_table = self.storage.load_all_rows()
        self._graph = build_graph(self._rows_by_table)
        title_by_table = {table_id: self.storage.table_title(table_id) for table_id in self.storage.known_tables()}
        self._tables = infer_tables(self._graph, self._rows_by_table, title_by_table)

    def _result(self, ok: bool, errors: list[str] | None = None, warnings: list[str] | None = None) -> dict[str, Any]:
        return {
            "ok": bool(ok),
            "errors": list(errors or []),
            "warnings": list(warnings or []),
        }

    def list_tables(self) -> list[dict[str, Any]]:
        out = []
        for table_id, table in sorted(self._tables.items(), key=lambda item: item[0]):
            out.append(
                {
                    "table_id": table_id,
                    "title": str(table.get("title") or table_id),
                    "layer": table.get("layer"),
                    "archetype_id": str(table.get("archetype_id") or ""),
                }
            )
        return out

    def _table(self, table_id: str) -> dict[str, Any] | None:
        return self._tables.get(str(table_id or "").strip())

    @staticmethod
    def _columns(rows: list[dict[str, str]]) -> list[str]:
        preferred = ["identifier", "reference", "magnitude", "label", "references", "msn_id", "name"]
        found: list[str] = []
        for key in preferred:
            for row in rows:
                if key in row and key not in META_FIELDS:
                    found.append(key)
                    break
        discovered: list[str] = []
        for row in rows:
            for key in row.keys():
                if key in META_FIELDS or key in found or key in discovered:
                    continue
                discovered.append(key)
        return found + discovered

    def list_instances(self, table_id: str) -> list[dict[str, Any]]:
        table = self._table(table_id)
        if not table:
            return []
        rows = list(table.get("rows") or [])
        instances = []
        for bucket in cluster_rows(rows):
            instances.append(
                {
                    "instance_id": str(bucket.get("instance_id") or ""),
                    "signature": list(bucket.get("signature") or []),
                    "row_count": len(bucket.get("rows") or []),
                }
            )
        return instances

    def _rows_for_instance(self, table_id: str, instance_id: str | None) -> list[dict[str, str]]:
        table = self._table(table_id)
        if not table:
            return []

        rows = list(table.get("rows") or [])
        if not instance_id:
            return rows

        for bucket in cluster_rows(rows):
            if str(bucket.get("instance_id") or "") == str(instance_id):
                return list(bucket.get("rows") or [])
        return []

    def get_view(self, table_id: str, instance_id: str | None = None, mode: str = "general") -> dict[str, Any]:
        table_key = str(table_id or "").strip()
        mode_token = str(mode or "general").strip().lower()
        errors: list[str] = []
        warnings: list[str] = []

        if mode_token not in {"general", "inspect"}:
            errors.append("mode must be one of: general, inspect")
            mode_token = "general"

        table = self._table(table_key)
        if not table:
            errors.append(f"Unknown table_id: {table_key}")
            return {
                "table": {"table_id": table_key, "title": table_key, "layer": None, "archetype_id": ""},
                "instance": {"instance_id": str(instance_id or ""), "signature": [], "row_count": 0},
                "mode": mode_token,
                "columns": [],
                "rows": [],
                "staged_edits": [],
                "errors": errors,
                "warnings": warnings,
            }

        rows = self._rows_for_instance(table_key, instance_id)
        columns = self._columns(rows)

        view_rows: list[dict[str, Any]] = []
        for row in rows:
            row_id = str(row.get("row_id") or "").strip()
            row_fields: dict[str, str] = {}
            row_staged: list[str] = []
            row_errors: list[str] = []
            row_warnings: list[str] = []

            for field_id in columns:
                lens = get_lens(field_id, self.config)
                raw_value = str(row.get(field_id) or "")
                display_value = lens.render(lens.decode(raw_value))
                staged_key = (table_key, row_id, field_id)
                if staged_key in self._staged:
                    display_value = self._staged[staged_key]
                    row_staged.append(field_id)
                row_fields[field_id] = display_value

            inspect_data: dict[str, Any] = {}
            if mode_token == "inspect":
                node_id = str(row.get("_node_id") or f"{table_key}:{row_id}")
                node = self._graph.get_node(node_id)
                if node:
                    chain = resolve_chain(self._graph, node.node_id)
                    constraint = compile_constraint(node, chain)
                    inspect_data = {
                        "node_id": node.node_id,
                        "chain": chain,
                        "constraint": constraint,
                    }
                    row_warnings.extend(constraint.get("warnings") or [])

            view_rows.append(
                {
                    "row_id": row_id,
                    "fields": row_fields,
                    "staged_fields": row_staged,
                    "errors": row_errors,
                    "warnings": row_warnings,
                    "inspect": inspect_data,
                }
            )

        staged_edits = [
            {
                "table_id": t,
                "row_id": r,
                "field_id": f,
                "display_value": value,
            }
            for (t, r, f), value in sorted(self._staged.items())
            if t == table_key
        ]

        active_instance = str(instance_id or "")
        if not active_instance and rows:
            clusters = cluster_rows(rows)
            if clusters:
                active_instance = str(clusters[0].get("instance_id") or "")

        return {
            "table": {
                "table_id": table_key,
                "title": str(table.get("title") or table_key),
                "layer": table.get("layer"),
                "archetype_id": str(table.get("archetype_id") or ""),
            },
            "instance": {
                "instance_id": active_instance,
                "signature": [],
                "row_count": len(rows),
            },
            "mode": mode_token,
            "columns": columns,
            "rows": view_rows,
            "staged_edits": staged_edits,
            "errors": errors,
            "warnings": warnings,
        }

    def stage_edit(self, table_id: str, row_id: str, field_id: str, display_value: str) -> dict[str, Any]:
        table_key = str(table_id or "").strip()
        row_key = str(row_id or "").strip()
        field_key = str(field_id or "").strip()

        if not table_key or not row_key or not field_key:
            return self._result(False, ["table_id, row_id, and field_id are required"], [])

        table = self._table(table_key)
        if not table:
            return self._result(False, [f"Unknown table_id: {table_key}"], [])

        rows = list(table.get("rows") or [])
        target_row = None
        for row in rows:
            if str(row.get("row_id") or "").strip() == row_key:
                target_row = row
                break
        if target_row is None:
            return self._result(False, [f"Unknown row_id: {row_key}"], [])

        allowed_fields = set(self._columns(rows))
        if field_key not in allowed_fields:
            return self._result(False, [f"Unknown field_id for table: {field_key}"], [])

        lens = get_lens(field_key, self.config)
        validation = lens.validate(str(display_value or ""))
        if not validation.ok:
            return self._result(False, list(validation.errors), list(validation.warnings))

        self._staged[(table_key, row_key, field_key)] = str(display_value or "")
        return self._result(True, [], list(validation.warnings))

    def revert_edit(self, table_id: str, row_id: str, field_id: str) -> dict[str, Any]:
        key = (str(table_id or "").strip(), str(row_id or "").strip(), str(field_id or "").strip())
        if not all(key):
            return self._result(False, ["table_id, row_id, and field_id are required"], [])

        if key in self._staged:
            self._staged.pop(key, None)
            return self._result(True, [], [])
        return self._result(True, [], ["No staged edit found for requested cell."])

    def reset_staging(self, table_id: str | None = None) -> dict[str, Any]:
        token = str(table_id or "").strip()
        if not token:
            self._staged.clear()
            return self._result(True, [], [])

        to_remove = [key for key in self._staged.keys() if key[0] == token]
        for key in to_remove:
            self._staged.pop(key, None)
        return self._result(True, [], [])

    def commit(self, table_id: str | None = None) -> dict[str, Any]:
        token = str(table_id or "").strip()
        pending = {
            key: value
            for key, value in self._staged.items()
            if not token or key[0] == token
        }
        if not pending:
            return self._result(True, [], ["no staged edits"])

        by_table: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        for key in pending.keys():
            by_table[key[0]].append(key)

        errors: list[str] = []
        for table_key, edit_keys in by_table.items():
            table = self._table(table_key)
            if not table:
                errors.append(f"Unknown table during commit: {table_key}")
                continue

            rows = [dict(row) for row in list(table.get("rows") or [])]
            by_row: dict[str, dict[str, str]] = {str(row.get("row_id") or "").strip(): row for row in rows}

            for _, row_id, field_id in edit_keys:
                target_row = by_row.get(row_id)
                if not target_row:
                    errors.append(f"Unknown row during commit: {table_key}/{row_id}")
                    continue
                lens = get_lens(field_id, self.config)
                encoded = lens.encode(self._staged[(table_key, row_id, field_id)])
                target_row[field_id] = encoded

            persist_result = self.storage.persist_rows(table_key, rows)
            if not persist_result.get("ok"):
                errors.extend(list(persist_result.get("errors") or []))

        if errors:
            return self._result(False, errors, [])

        for key in pending.keys():
            self._staged.pop(key, None)

        self._reload()
        return self._result(True, [], [])

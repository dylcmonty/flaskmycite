from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from data.engine.constraints import compile_constraint, resolve_chain
from data.engine.graph import META_FIELDS, build_graph, summarize_node
from data.engine.lenses import get_lens
from data.engine.nimm.directives import parse_directive
from data.engine.nimm.state import DataViewState, normalize_mode, normalize_source
from data.engine.nimm.viewmodels import empty_pane, pane, response_payload
from data.engine.tables import cluster_rows, infer_tables


class Workspace:
    def __init__(self, storage_backend, config: dict[str, Any] | None = None):
        self.storage = storage_backend
        self.config = config or {}

        self._state_path = self._resolve_state_path()
        self._startup_warnings: list[str] = []

        self._staged: dict[tuple[str, str, str], str] = {}
        self._rows_by_table: dict[str, list[dict[str, str]]] = {}
        self._tables: dict[str, dict[str, Any]] = {}
        self._graph = build_graph({})

        self._reload()
        self._state = self._load_state()
        self._sync_staging_from_state()
        self._sync_state_staging()
        self._persist_state()

    def _resolve_state_path(self) -> Path | None:
        token = self.config.get("state_path")
        if not token:
            return None
        try:
            return Path(str(token))
        except Exception:
            return None

    def _default_focus_source(self) -> str:
        return normalize_source(str(self.config.get("default_focus_source") or "auto"), "auto")

    def _default_mode(self) -> str:
        return normalize_mode(str(self.config.get("default_mode") or "general"), "general")

    def _default_lens(self) -> str:
        token = str(self.config.get("default_lens") or "default").strip().lower()
        return token or "default"

    def _default_state(self) -> DataViewState:
        return DataViewState(
            focus_source=self._default_focus_source(),
            focus_subject="",
            left_pane=empty_pane(),
            right_pane=empty_pane(),
            mode=self._default_mode(),
            lens_context={"default": self._default_lens(), "overrides": {}},
            staged_edits={},
            validation_errors=[],
            selection={},
        )

    def _load_state(self) -> DataViewState:
        if self._state_path is None:
            return self._default_state()

        if not self._state_path.exists() or not self._state_path.is_file():
            return self._default_state()

        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
            state = DataViewState.from_dict(
                payload,
                default_focus_source=self._default_focus_source(),
                default_mode=self._default_mode(),
                default_lens=self._default_lens(),
            )
            return state
        except Exception:
            self._startup_warnings.append("state_recovered_from_malformed_payload")
            return self._default_state()

    def _persist_state(self) -> None:
        if self._state_path is None:
            return
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(json.dumps(self._state.to_dict(), indent=2) + "\n", encoding="utf-8")
        except Exception:
            return

    def _reload(self) -> None:
        self._rows_by_table = self.storage.load_all_rows()
        self._graph = build_graph(self._rows_by_table)
        title_by_table = {table_id: self.storage.table_title(table_id) for table_id in self.storage.known_tables()}
        self._tables = infer_tables(self._graph, self._rows_by_table, title_by_table)

    def _sync_staging_from_state(self) -> None:
        staged = self._state.staged_edits if isinstance(self._state.staged_edits, dict) else {}
        out: dict[tuple[str, str, str], str] = {}
        for _, item in staged.items():
            if not isinstance(item, dict):
                continue
            table_id = str(item.get("table_id") or "").strip()
            row_id = str(item.get("row_id") or "").strip()
            field_id = str(item.get("field_id") or "").strip()
            value = str(item.get("display_value") or "")
            if table_id and row_id and field_id:
                out[(table_id, row_id, field_id)] = value
        self._staged = out

    def _sync_state_staging(self) -> None:
        staged: dict[str, dict[str, str]] = {}
        for table_id, row_id, field_id in sorted(self._staged.keys()):
            token = f"{table_id}|{row_id}|{field_id}"
            staged[token] = {
                "table_id": table_id,
                "row_id": row_id,
                "field_id": field_id,
                "display_value": self._staged[(table_id, row_id, field_id)],
            }
        self._state.staged_edits = staged

    def _table(self, table_id: str) -> dict[str, Any] | None:
        return self._tables.get(str(table_id or "").strip())

    def _fallback_table_id(self) -> str:
        selected = str((self._state.selection or {}).get("table_id") or "").strip()
        if selected and selected in self._tables:
            return selected
        known = sorted(self._tables.keys())
        return known[0] if known else ""

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

    def _rows_for_instance(self, table_id: str, instance_id: str | None) -> list[dict[str, str]]:
        table = self._table(table_id)
        if table is None:
            return []

        rows = list(table.get("rows") or [])
        if not instance_id:
            return rows

        for bucket in cluster_rows(rows):
            if str(bucket.get("instance_id") or "") == str(instance_id):
                return list(bucket.get("rows") or [])
        return []

    def list_tables(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
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

    def list_instances(self, table_id: str) -> list[dict[str, Any]]:
        table = self._table(table_id)
        if table is None:
            return []

        rows = list(table.get("rows") or [])
        out = []
        for bucket in cluster_rows(rows):
            out.append(
                {
                    "instance_id": str(bucket.get("instance_id") or ""),
                    "signature": list(bucket.get("signature") or []),
                    "row_count": len(bucket.get("rows") or []),
                }
            )
        return out

    def get_view(self, table_id: str, instance_id: str | None = None, mode: str = "general") -> dict[str, Any]:
        table_key = str(table_id or "").strip()
        mode_token = normalize_mode(mode, self._default_mode())

        errors: list[str] = []
        warnings: list[str] = []

        table = self._table(table_key)
        if table is None:
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
                lens = get_lens(field_id, lens_context=self._state.lens_context, config=self.config)
                raw_value = str(row.get(field_id) or "")
                display_value = lens.render(lens.decode(raw_value))

                staged_key = (table_key, row_id, field_id)
                if staged_key in self._staged:
                    display_value = self._staged[staged_key]
                    row_staged.append(field_id)

                row_fields[field_id] = display_value

            inspect = {}
            if mode_token == "inspect":
                node_id = str(row.get("_node_id") or f"{table_key}:{row_id}")
                node = self._graph.get_node(node_id)
                if node is not None:
                    chain = resolve_chain(self._graph, node.node_id)
                    constraint = compile_constraint(node, chain)
                    row_warnings.extend(list(constraint.get("warnings") or []))
                    inspect = {"chain": chain, "constraint": constraint}

            view_rows.append(
                {
                    "row_id": row_id,
                    "fields": row_fields,
                    "staged_fields": row_staged,
                    "errors": row_errors,
                    "warnings": row_warnings,
                    "inspect": inspect,
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

        return {
            "table": {
                "table_id": table_key,
                "title": str(table.get("title") or table_key),
                "layer": table.get("layer"),
                "archetype_id": str(table.get("archetype_id") or ""),
            },
            "instance": {
                "instance_id": str(instance_id or ""),
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

    def _node_for_subject(self, subject: str):
        token = str(subject or "").strip()
        if not token:
            return None
        direct = self._graph.get_node(token)
        if direct is not None:
            return direct
        matches = self._graph.find_by_identifier(token)
        if not matches:
            return None
        return self._graph.get_node(matches[0])

    def _table_for_subject(self, subject: str) -> dict[str, Any] | None:
        token = str(subject or "").strip()
        if not token:
            return None

        direct = self._table(token)
        if direct is not None:
            return direct

        for table in self._tables.values():
            archetype_id = str(table.get("archetype_id") or "").strip()
            archetype_identifier = str(table.get("archetype_identifier") or "").strip()
            if token in {archetype_id, archetype_identifier}:
                return table

        return None

    def _nav_payload(self, source: str, args: dict[str, Any]) -> dict[str, Any]:
        token = normalize_source(source, "auto")
        payload: dict[str, Any] = {"source": token}

        if token == "anthology":
            nodes = [self._graph.get_node(node_id) for node_id in self._graph.find_by_source("anthology")]
            nodes = [node for node in nodes if node is not None]
            layers: dict[int, int] = defaultdict(int)
            recent: list[dict[str, Any]] = []
            for node in nodes[:50]:
                if node.layer is not None:
                    layers[node.layer] += 1
                recent.append({"identifier": node.identifier, "label": node.label, "node_id": node.node_id})

            payload["table_archetypes"] = [
                {
                    "table_id": item.get("table_id"),
                    "title": item.get("title"),
                    "layer": item.get("layer"),
                    "archetype_id": item.get("archetype_id"),
                }
                for item in self.list_tables()
                if str(item.get("archetype_id") or "")
            ]
            payload["recent_datums"] = recent
            payload["layer_filters"] = [{"layer": layer, "count": count} for layer, count in sorted(layers.items())]
            return payload

        if token == "conspectus":
            nodes = [self._graph.get_node(node_id) for node_id in self._graph.find_by_source("conspectus")]
            payload["selection_mappings"] = [
                {
                    "identifier": node.identifier,
                    "label": node.label,
                    "references": node.raw.get("references", ""),
                    "node_id": node.node_id,
                }
                for node in nodes
                if node is not None
            ]
            return payload

        if token == "samras":
            page = int(args.get("page") or 1)
            page_size = int(args.get("page_size") or 50)
            if page < 1:
                page = 1
            if page_size < 1:
                page_size = 50

            nodes = [self._graph.get_node(node_id) for node_id in self._graph.find_by_source("samras")]
            nodes = [node for node in nodes if node is not None]

            start = (page - 1) * page_size
            end = start + page_size
            payload["page"] = page
            payload["page_size"] = page_size
            payload["total"] = len(nodes)
            payload["nodes"] = [
                {
                    "msn_id": node.raw.get("msn_id", node.identifier),
                    "name": node.raw.get("name", node.label),
                    "node_id": node.node_id,
                }
                for node in nodes[start:end]
            ]
            return payload

        payload["sources"] = {
            "anthology": len(self._graph.find_by_source("anthology")),
            "conspectus": len(self._graph.find_by_source("conspectus")),
            "samras": len(self._graph.find_by_source("samras")),
        }
        payload["tables"] = self.list_tables()
        return payload

    def _state_response(self, errors: list[str] | None = None, warnings: list[str] | None = None) -> dict[str, Any]:
        staged_list = list((self._state.staged_edits or {}).values())
        merged_warnings = list(self._startup_warnings)
        if warnings:
            merged_warnings.extend(list(warnings))

        return response_payload(
            state=self._state.to_dict(),
            left_pane_vm=dict(self._state.left_pane),
            right_pane_vm=dict(self._state.right_pane),
            errors=list(errors or []),
            warnings=merged_warnings,
            staged_edits=staged_list,
        )

    def get_state_snapshot(self) -> dict[str, Any]:
        return self._state_response()

    def apply_directive(self, payload: dict[str, Any] | str) -> dict[str, Any]:
        parsed = parse_directive(payload)
        errors = list(parsed.errors)
        warnings = list(parsed.warnings)

        if errors:
            return self._state_response(errors=errors, warnings=warnings)

        action = parsed.action
        subject = parsed.subject
        method = parsed.method
        args = parsed.args

        if action == "nav":
            source = normalize_source(subject or args.get("source") or self._state.focus_source, self._default_focus_source())
            self._state.focus_source = source
            self._state.focus_subject = ""
            self._state.left_pane = pane("navigation", self._nav_payload(source, args))
            self._state.right_pane = empty_pane("investigation")

        elif action == "inv":
            self._state.focus_subject = subject
            method_token = str(method or "summary").strip().lower() or "summary"

            node = self._node_for_subject(subject)
            if method_token == "summary":
                if node is None:
                    errors.append(f"Unknown datum subject: {subject}")
                else:
                    self._state.right_pane = pane("datum_summary", {"datum": summarize_node(node)})

            elif method_token == "abstraction_path":
                if node is None:
                    errors.append(f"Unknown datum subject: {subject}")
                else:
                    chain = resolve_chain(self._graph, node.node_id)
                    self._state.right_pane = pane(
                        "abstraction_path",
                        {
                            "subject": subject,
                            "chain": chain,
                        },
                    )

            elif method_token == "instances":
                table = self._table_for_subject(subject)
                if table is None:
                    errors.append(f"Unknown table/archetype subject: {subject}")
                else:
                    table_id = str(table.get("table_id") or "")
                    self._state.selection["table_id"] = table_id
                    self._state.right_pane = pane(
                        "table_instances",
                        {
                            "table": {
                                "table_id": table_id,
                                "title": table.get("title"),
                                "layer": table.get("layer"),
                                "archetype_id": table.get("archetype_id"),
                            },
                            "instances": self.list_instances(table_id),
                        },
                    )

            else:
                errors.append(f"Unsupported inv method: {method_token}")

        elif action == "med":
            method_token = str(method or "").strip().lower()
            if method_token.startswith("mode="):
                mode_token = method_token.split("=", 1)[1].strip().lower()
            else:
                mode_token = str(args.get("mode") or "").strip().lower()

            if mode_token:
                if mode_token not in {"general", "inspect", "raw", "inferred"}:
                    errors.append("mode must be one of: general, inspect, raw, inferred")
                else:
                    self._state.mode = mode_token

            if method_token.startswith("lens="):
                lens_id = method_token.split("=", 1)[1].strip().lower()
            else:
                lens_id = str(args.get("lens") or "").strip().lower()
            if lens_id:
                self._state.lens_context["default"] = lens_id

        elif action == "man":
            method_token = str(method or "").strip().lower()
            if method_token in {"edit_cell", "stage_edit"}:
                result = self.stage_edit(
                    row_id=str(args.get("row_id") or ""),
                    field_id=str(args.get("field_id") or ""),
                    display_value=str(args.get("new_value") or args.get("display_value") or ""),
                    table_id=str(args.get("table_id") or subject or "") or None,
                    instance_id=str(args.get("instance_id") or "") or None,
                )
                errors.extend(list(result.get("errors") or []))
                warnings.extend(list(result.get("warnings") or []))
            elif method_token == "commit":
                result = self.commit(
                    scope=str(args.get("scope") or "all"),
                    table_id=str(args.get("table_id") or subject or "") or None,
                    row_id=str(args.get("row_id") or "") or None,
                )
                errors.extend(list(result.get("errors") or []))
                warnings.extend(list(result.get("warnings") or []))
            elif method_token in {"reset", "reset_staging"}:
                result = self.reset_staging(
                    scope=str(args.get("scope") or "all"),
                    table_id=str(args.get("table_id") or subject or "") or None,
                    row_id=str(args.get("row_id") or "") or None,
                )
                errors.extend(list(result.get("errors") or []))
                warnings.extend(list(result.get("warnings") or []))
            else:
                errors.append(f"Unsupported man method: {method_token}")

        self._state.validation_errors = list(errors)
        self._sync_state_staging()
        self._persist_state()
        return self._state_response(errors=errors, warnings=warnings)

    def stage_edit(
        self,
        row_id: str,
        field_id: str,
        display_value: str,
        table_id: str | None = None,
        instance_id: str | None = None,
    ) -> dict[str, Any]:
        table_key = str(table_id or self._fallback_table_id()).strip()
        row_key = str(row_id or "").strip()
        field_key = str(field_id or "").strip()

        if not table_key:
            return {"ok": False, "errors": ["No table selected."], "warnings": []}
        if not row_key or not field_key:
            return {"ok": False, "errors": ["row_id and field_id are required."], "warnings": []}

        rows = self._rows_for_instance(table_key, instance_id)
        row_match = None
        for row in rows:
            if str(row.get("row_id") or "").strip() == row_key:
                row_match = row
                break

        if row_match is None:
            return {"ok": False, "errors": [f"Unknown row_id: {row_key}"], "warnings": []}

        columns = set(self._columns(rows))
        if field_key not in columns:
            return {"ok": False, "errors": [f"Unknown field_id for table: {field_key}"], "warnings": []}

        lens = get_lens(field_key, lens_context=self._state.lens_context, config=self.config)
        validation = lens.validate(str(display_value or ""))
        if not validation.ok:
            return {"ok": False, "errors": list(validation.errors), "warnings": list(validation.warnings)}

        warnings = list(validation.warnings)
        node_id = str(row_match.get("_node_id") or "")
        node = self._graph.get_node(node_id)
        if node is not None:
            chain = resolve_chain(self._graph, node.node_id)
            constraint = compile_constraint(node, chain)
            warnings.extend(list(constraint.get("warnings") or []))
            if constraint.get("errors"):
                return {
                    "ok": False,
                    "errors": list(constraint.get("errors") or []),
                    "warnings": warnings,
                }

        self._staged[(table_key, row_key, field_key)] = str(display_value or "")
        self._state.selection = {
            "table_id": table_key,
            "row_id": row_key,
            "field_id": field_key,
            "instance_id": str(instance_id or ""),
        }
        self._sync_state_staging()
        self._persist_state()
        return {"ok": True, "errors": [], "warnings": warnings}

    def revert_edit(self, table_id: str, row_id: str, field_id: str) -> dict[str, Any]:
        key = (str(table_id or "").strip(), str(row_id or "").strip(), str(field_id or "").strip())
        if not all(key):
            return {"ok": False, "errors": ["table_id, row_id, and field_id are required."], "warnings": []}

        if key not in self._staged:
            return {"ok": True, "errors": [], "warnings": ["No staged edit found for requested cell."]}

        self._staged.pop(key, None)
        self._sync_state_staging()
        self._persist_state()
        return {"ok": True, "errors": [], "warnings": []}

    def reset_staging(self, scope: str = "all", table_id: str | None = None, row_id: str | None = None) -> dict[str, Any]:
        scope_token = str(scope or "all").strip().lower()
        table_key = str(table_id or self._fallback_table_id()).strip()
        row_key = str(row_id or "").strip()

        if scope_token not in {"all", "table", "row"}:
            return {"ok": False, "errors": ["scope must be one of: all, table, row"], "warnings": []}

        if scope_token == "all":
            self._staged.clear()
        elif scope_token == "table":
            if not table_key:
                return {"ok": False, "errors": ["No table selected for table-scope reset."], "warnings": []}
            for key in [k for k in self._staged if k[0] == table_key]:
                self._staged.pop(key, None)
        else:
            if not table_key or not row_key:
                return {"ok": False, "errors": ["table_id and row_id are required for row scope reset."], "warnings": []}
            for key in [k for k in self._staged if k[0] == table_key and k[1] == row_key]:
                self._staged.pop(key, None)

        self._sync_state_staging()
        self._persist_state()
        return {"ok": True, "errors": [], "warnings": []}

    def commit(self, scope: str = "all", table_id: str | None = None, row_id: str | None = None) -> dict[str, Any]:
        scope_token = str(scope or "all").strip().lower()
        table_key = str(table_id or self._fallback_table_id()).strip()
        row_key = str(row_id or "").strip()

        if scope_token not in {"all", "table", "row"}:
            return {"ok": False, "errors": ["scope must be one of: all, table, row"], "warnings": []}

        pending: dict[tuple[str, str, str], str] = {}
        for key, value in self._staged.items():
            key_table, key_row, _ = key
            include = False
            if scope_token == "all":
                include = True
            elif scope_token == "table":
                include = bool(table_key and key_table == table_key)
            elif scope_token == "row":
                include = bool(table_key and row_key and key_table == table_key and key_row == row_key)
            if include:
                pending[key] = value

        if not pending:
            return {"ok": True, "errors": [], "warnings": ["no staged edits"]}

        validation_errors: list[str] = []
        validation_warnings: list[str] = []
        for (table_token, row_token, field_token), display_value in pending.items():
            lens = get_lens(field_token, lens_context=self._state.lens_context, config=self.config)
            validation = lens.validate(display_value)
            if not validation.ok:
                for err in validation.errors:
                    validation_errors.append(f"{table_token}/{row_token}/{field_token}: {err}")
            validation_warnings.extend(list(validation.warnings))

        if validation_errors:
            return {"ok": False, "errors": validation_errors, "warnings": validation_warnings}

        by_table: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        for key in pending.keys():
            by_table[key[0]].append(key)

        persist_errors: list[str] = []
        known_storage_tables = {str(item).strip().lower() for item in self.storage.known_tables()}
        for target_table, edit_keys in by_table.items():
            table = self._table(target_table)
            if table is None:
                persist_errors.append(f"Unknown table during commit: {target_table}")
                continue

            normalized_target = str(target_table or "").strip().lower()
            if normalized_target in known_storage_tables:
                rows = [dict(row) for row in list(table.get("rows") or [])]
                by_row = {str(row.get("row_id") or "").strip(): row for row in rows}

                for _, target_row, target_field in edit_keys:
                    row_payload = by_row.get(target_row)
                    if row_payload is None:
                        persist_errors.append(f"Unknown row during commit: {target_table}/{target_row}")
                        continue
                    lens = get_lens(target_field, lens_context=self._state.lens_context, config=self.config)
                    row_payload[target_field] = lens.encode(self._staged[(target_table, target_row, target_field)])

                result = self.storage.persist_rows(normalized_target, rows)
                if not bool(result.get("ok")):
                    persist_errors.extend(list(result.get("errors") or []))
                continue

            # Inferred/archetype table ids are persisted back to their source payloads.
            source_rows: dict[str, list[dict[str, str]]] = {}
            source_row_lookup: dict[str, dict[str, dict[str, str]]] = {}
            row_source: dict[str, str] = {}

            for row in list(table.get("rows") or []):
                row_id_token = str(row.get("row_id") or "").strip()
                source_token = str(row.get("_source") or "").strip().lower()
                if not row_id_token or not source_token:
                    continue
                row_source[row_id_token] = source_token
                if source_token not in source_rows:
                    source_payload_rows = [dict(item) for item in list(self._rows_by_table.get(source_token) or [])]
                    source_rows[source_token] = source_payload_rows
                    source_row_lookup[source_token] = {
                        str(item.get("row_id") or "").strip(): item for item in source_payload_rows
                    }

            touched_sources: set[str] = set()
            for _, target_row, target_field in edit_keys:
                source_token = row_source.get(target_row)
                if not source_token:
                    persist_errors.append(f"Unable to resolve source table for row: {target_table}/{target_row}")
                    continue
                if source_token not in known_storage_tables:
                    persist_errors.append(f"Unknown source table during commit: {source_token}")
                    continue

                source_row = source_row_lookup.get(source_token, {}).get(target_row)
                if source_row is None:
                    persist_errors.append(f"Unknown source row during commit: {source_token}/{target_row}")
                    continue

                lens = get_lens(target_field, lens_context=self._state.lens_context, config=self.config)
                source_row[target_field] = lens.encode(self._staged[(target_table, target_row, target_field)])
                touched_sources.add(source_token)

            for source_token in sorted(touched_sources):
                result = self.storage.persist_rows(source_token, source_rows.get(source_token, []))
                if not bool(result.get("ok")):
                    persist_errors.extend(list(result.get("errors") or []))

        if persist_errors:
            return {"ok": False, "errors": persist_errors, "warnings": validation_warnings}

        for key in pending.keys():
            self._staged.pop(key, None)

        self._reload()
        self._sync_state_staging()
        self._persist_state()
        return {"ok": True, "errors": [], "warnings": validation_warnings}

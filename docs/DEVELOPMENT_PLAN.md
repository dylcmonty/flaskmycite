# Development Plan

## Current State Summary

### Portal inventory and role

- Demo/reference portals:
  - `mycite-ne-example`
  - `mycite-le-example`
- Company portal:
  - `mycite-le_fnd`
- Client portal:
  - `mycite-le_cvcc`
- Demo/user portals:
  - `mycite-ne_mw`
  - `mycite-ne_dm`
- Lightweight state folders without app runtime:
  - `mycite-le_tff`
  - `mycite-ne_dg`
  - `mycite-ne_eb`
  - `mycite-ne_jt`
  - `mycite-ne_ks`
  - `mycite-ne_mt`

### Implemented capabilities (code-accurate)

- Request log + portal inbox APIs:
  - Implemented in `mycite-ne-example`, `mycite-le-example`, `mycite-ne_mw`, `mycite-le_fnd`
- Contracts APIs:
  - Implemented in `mycite-ne-example`, `mycite-le-example`, `mycite-ne_mw`, `mycite-le_fnd`
- External signed inbox (`/api/inbox/<msn_id>`):
  - Implemented in `mycite-ne-example`, `mycite-le-example`, `mycite-ne_mw`
  - Not wired in `mycite-le_fnd`, `mycite-le_cvcc`, `mycite-ne_dm`
- Alias interface/session routes (`/portal/alias/<alias_id>`):
  - Implemented across active app instances (`ne-example`, `le-example`, `le_fnd`, `le_cvcc`, `ne_mw`, `ne_dm`)
- LE embed endpoints:
  - `/portal/embed/poc` in `mycite-le-example`, `mycite-le_fnd`, `mycite-le_cvcc`
  - `/portal/embed/tenant` in `mycite-le_fnd`
- Progeny config scaffolding:
  - Wired in `mycite-ne-example`, `mycite-le-example`, `mycite-le_fnd`
- Magnetlink/tool scaffolding:
  - Magnetlinks APIs wired where contract/inbox stack is present
  - `mycite-le_fnd` includes PayPal demo tool wiring
- Data tab / data module status:
  - `mycite-le_fnd` includes `data/data.py` JSON-backed loader and portal table views
  - Table update endpoint is currently non-persistent (`501 Not implemented`)

## Intended Operational Model

- Public contact card boundary:
  - `GET /<msn_id>.json` returns public-safe profile data only.
- Portal-only boundary:
  - `/portal/**` serves UI and control-plane APIs.
- Signed external API boundary:
  - `/api/**` is for machine-to-machine signed interactions without portal session login.
- Contract workflow + auditing:
  - Contract lifecycle events and request exchange are logged to NDJSON request logs.
  - See canonical detail in [`request_log_and_contracts.md`](request_log_and_contracts.md).
- Alias + progeny model:
  - Alias session UI + progeny overlays provide organization-context operations.
  - See supporting model notes in [`mss_notes.md`](mss_notes.md).

## Near-Term Milestones (MVP)

- Make example portals authoritative reference implementations.
- Propagate example parity into non-example portals in controlled increments.
- Finish alias/progeny MVP for tenant view in `mycite-le_fnd`.
- Extend FND data tab from JSON-backed editor to include lens-system skeleton.
- Normalize config-driven tool-tab runtime so optional tools appear on Home as self-contained panels without core UI rewrites.
- Land tool-packaged NIMM Data Tool (`data_tool`) with stable `/portal/api/data/*` endpoints.

## Work Breakdown (Actionable Checklist)

### API parity

- [ ] Align non-example portal API wiring with example portal baseline.
- [ ] Add missing external signed inbox wiring where required.
- [ ] Standardize options metadata exposure across portal API routes.

### UI parity

- [ ] Keep base shell, nav, and tab behavior aligned to example portals.
- [ ] Complete `mycite-le_fnd` client/tenant edit and embed workflow polish.
- [ ] Ensure portal pages degrade safely when optional tools are unavailable.

### Data and lenses

- [ ] Keep read/write adapter logic isolated in `data/storage_json.py` (JSON now; swappable later).
- [ ] Keep Data Tool semantics in `data/engine/*` and `data/engine/nimm/*` with no Flask imports.
- [ ] Keep controller glue thin in `portal/api/data_workspace.py`.
- [ ] Keep lens registry baseline (`default`, `ascii`) in examples; load experiments only in FND behind config.
- [ ] Land datum SVG icon support via presentation sidecar (`data/presentation/datum_icons.json`) + picker UI and `/portal/api/data/icons/list`.
- [ ] Define migration interface from JSON storage to DB-backed adapters.

### Tools and magnetlinks

- [ ] Normalize magnetlink route behavior and docs across portals.
- [ ] Keep tool modules optional and explicitly wired through `enabled_tools` + `portal/tools/runtime.py`.
- [ ] Ensure tool tabs are Home-tab plugins with route-backed/self-contained UI surfaces.
- [ ] Separate tool UI concerns from signed outbound/inbound operational logic.

### Docs and tests

- [ ] Keep canonical architecture docs in `/docs` and link from root/example READMEs.
- [ ] Add basic route-level smoke tests for active app instances.
- [ ] Add docs verification checks to prevent drift.

## Repo Conventions

### Config and storage layout

- `public/`: public-safe contact artifacts
- `private/`: config, aliases, contracts, request logs
- `data/`: cache/queue/derived artifacts
- `vault/`: secret-handling conventions and refs (no secrets committed)

### Must not be committed

- Vault key material and private credentials.
- Runtime logs and PID artifacts (`.flask-multi/logs`, `.flask-multi/pids` outputs).
- Ephemeral caches and generated artifacts that are not intended source-of-truth.

### Local run conventions

- Launcher script: `./flask_apps.sh`
- Current launcher ports:
  - `mycite-ne_mw`: `5000`
  - `mycite-le_cvcc`: `5001`
  - `mycite-le_fnd`: `5002`
- App-local defaults in each `app.py` may differ; use launcher mapping for multi-app local runs.


---

## Data Tool: NIMM directives, state, and tool packaging

This section captures the **intent** for the Data tool to function as a sturdy, extensible interface (not a one-off table viewer) and the **non-binding implementation guidance** for achieving that intent within the portal/tool system.

### Intent

- The Data tab should behave as a tool-like surface whose behavior is governed by a small set of action categories:
  - `nav` (navigation), `inv` (investigation), `med` (mediation), `man` (manipulation).
- The Data tool should maintain an explicit internal **state** (location/focus, panes, mode, lens selection, staged edits) that drives what is rendered.
- “Tables” should be treated as **emergent** (soft grouping by row-signature), while field value validity remains **hard** (constraint/lens validation on write).
- Lenses must be first-class: multiple organizations or developers should be able to add lenses without rewriting the core UI.

### Implementation guidance (non-binding)

- Model NIMM as a small “command” interface:
  - Controllers accept a directive (action + subject + method/context).
  - Engine applies the directive to a workspace/session state.
  - Engine returns a view model for left/right panes and any validation state.
- Keep separation of responsibility:
  - `data/` code computes meaning, produces view models, stages/commits edits.
  - `/portal/api/` provides a stable HTTP interface to apply directives and edits.
  - UI templates/JS render view models and dispatch directives.
- Use two-pane layout as the first stable UX:
  - left = navigation context
  - right = investigation context
- Prefer storage adapters:
  - JSON-backed adapter now (anthology/conspectus/SAMRAS)
  - DB-backed adapter later, keeping the engine interface stable.

### Current implementation checkpoint

- `data_tool` is a runtime-loaded tool package under `portal/tools/data_tool`.
- Canonical API for the Data Tool is under `/portal/api/data/*`:
  - `POST /portal/api/data/directive`
  - `GET /portal/api/data/state`
  - `POST /portal/api/data/stage_edit`
  - `POST /portal/api/data/reset_staging`
  - `POST /portal/api/data/commit`
- Example portals keep deprecated table-centric shim endpoints temporarily for compatibility.

### Development isolation policy

- Example portals (`mycite-ne-example`, `mycite-le-example`) remain the stable reference for:
  - portal boundaries
  - contract/request-log behavior
  - minimal data tool scaffolding (engine/controller/UI separation)
- FND portal (`mycite-le_fnd`) may host experimental development:
  - additional lenses
  - prototype directive variants
  - more aggressive inference heuristics
  - richer UI exploration modes
- Experimental features should be:
  - isolated under FND-only modules, or
  - gated behind config flags

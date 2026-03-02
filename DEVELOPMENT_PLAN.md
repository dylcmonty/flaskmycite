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

- [ ] Keep all FND data read/write abstractions in `mycite-le_fnd/data/data.py`.
- [ ] Add lens registry skeleton and constraint-aware formatting hooks.
- [ ] Define migration interface from JSON storage to DB-backed adapters.

### Tools and magnetlinks

- [ ] Normalize magnetlink route behavior and docs across portals.
- [ ] Keep tool modules optional and explicitly wired through `enabled_tools` + `portal/tools/runtime.py`.
- [ ] Ensure tool tabs are Home-tab plugins with route-backed/self-contained UI surfaces.
- [ ] Separate tool UI concerns from signed outbound/inbound operational logic.

### Docs and tests

- [ ] Keep canonical docs root-based and linked from all example/non-example READMEs.
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

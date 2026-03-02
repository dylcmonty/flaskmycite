# Request Log and Contracts (Canonical)

This is the canonical operational summary for request logging and contract workflows across MyCite portals.

Historical draft detail remains in [`archive/request_log_and_contracts.md`](archive/request_log_and_contracts.md).

## Purpose

- Define how portals log inbound/outbound operational events.
- Define contract metadata flow without storing secret material in repo-tracked JSON.
- Keep boundaries explicit between public routes, portal-only routes, and external signed routes.

## Boundary model

- Public anonymous surface: `GET /<msn_id>.json`
- Portal-only surface: `/portal/**`
- External machine-to-machine surface (signed): `/api/**`

## Operational stores

- Request log (append-only NDJSON):
  - `private/request_log/<msn_id>.ndjson`
- Contract metadata (no secrets):
  - `private/contracts/contract-<contract_id>.json`
- Queue/cache artifacts:
  - `data/queue/*`
  - `data/cache/*`

## Request log requirements

- One JSON object per line.
- Append-only writes.
- No secret material (`private_key`, `hmac_key`, tokens, passwords).
- Include stable event metadata (`type`, `status`, timestamp, local `msn_id`, counterparty ids when applicable).

## Contract lifecycle (current model)

- Offer created by initiator portal (metadata written locally, status pending).
- Offer delivered through external signed message surface.
- Receiver logs offer event and keeps payload reference in private/data stores.
- Accept/decline updates contract metadata and writes audit events.

## Provider-held encrypted secrets (tenant PayPal config)

- FND tenant profiles keep PayPal configuration in:
  - `mycite-le_fnd/private/progeny/tenant/tenant-<tenant_msn_id>-under-<contract_id>.json`
- `paypal.client_secret` is never stored in plaintext.
  - Stored shape: `paypal.client_secret_enc.{alg,kid,nonce_b64,ciphertext_b64}`
- Contract-scoped encryption keys are local-only in:
  - `mycite-le_fnd/private/vault/contracts/<contract_id>.key`
- Logging policy:
  - request log events may include non-sensitive fields (tenant id, contract id, client id, webhook target/event mask)
  - request log events must not include plaintext secrets, ciphertext, key material, or nonce values
- UI flow:
  - client/alias sessions embed FND tenant window at `/portal/embed/tenant?...`
  - Payment Processing tab is functional; Service Agreement/Analytics/Blog tabs are placeholders

## Board workspace progeny type (CVCC provider)

- Provider: `mycite-le_cvcc`
- Consumers: board_member alias sessions embedding CVCC workspace
- Embed URL:
  - `/portal/embed/board_member?member_msn_id=<member>&as_alias_id=<alias>&tab=streams`
- Storage model:
  - streams journal: `mycite-le_cvcc/private/workspaces/board/v1/streams.ndjson`
  - calendar journal: `mycite-le_cvcc/private/workspaces/board/v1/calendar.ndjson`
  - people list (seed/fallback): `mycite-le_cvcc/private/workspaces/board/v1/people.json`
- Event attribution:
  - every write includes `author_msn_id`
- MVP access model:
  - membership check requires `member_msn_id` to resolve in CVCC board_member people/progeny materialization
- Auditing:
  - writes append request-log events (`workspace.streams.post.created`, `workspace.calendar.event.created`)
  - logs include operational metadata only; no secret material

## Data engine separation (example portals)

- Example portals expose portal-only data endpoints under `/portal/api/data/*`:
  - `GET /portal/api/data/tables`
  - `GET /portal/api/data/table/<table_id>/instances`
  - `GET /portal/api/data/table/<table_id>/view`
  - `POST /portal/api/data/stage_edit`
  - `POST /portal/api/data/revert_edit`
  - `POST /portal/api/data/reset`
  - `POST /portal/api/data/commit`
- Controller layer (`portal/api/data_workspace.py`) remains thin and delegates logic to engine modules.
- Data engine and storage layers (`data/engine/*`, `data/storage_json.py`) do not import Flask or template concerns.
- UI (`portal/ui/templates/data/*`, `portal/ui/static/data/data.js`) renders API-provided view models only; no direct JSON file access.

## Implementation status (repo reality)

- Portal inbox/read-log APIs exist on example portals and selected non-example instances.
- Contracts APIs are wired on `mycite-ne-example`, `mycite-le-example`, `mycite-ne_mw`, and `mycite-le_fnd`.
- External signed inbox route `/api/inbox/<msn_id>` is wired on:
  - `mycite-ne-example`
  - `mycite-le-example`
  - `mycite-ne_mw`

## References

- Boundary and data model notes: [`mss_notes.md`](mss_notes.md)
- Near-term implementation priorities: [`DEVELOPMENT_PLAN.md`](DEVELOPMENT_PLAN.md)
- Documentation ownership: [`DOCUMENTATION_POLICY.md`](DOCUMENTATION_POLICY.md)

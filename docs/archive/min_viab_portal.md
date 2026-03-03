# min_viab_portal.md

This document defines the **minimum viable portal implementation** for the MyCite prototype, in a precise, file-by-file way.
It assumes your current working local portal shell and APIs exist, and it focuses on: security boundaries, inbound request crypto + contract lifecycle,
tools placeholders, and NDJSON operational storage.

The sections below are in **logical implementation order** (build top to bottom).

---

## 0) Invariants and namespaces

**Goal:** Keep the architecture consistent while you iterate.

### Route namespaces (invariant)
- **Public (anonymous):** `GET /<msn_id>.json` only
- **Portal-only (authenticated later):** everything under `/portal/**`
- **Externally callable but signed (no portal session):** everything under `/api/**`

### Data boundaries (invariant)
- `public/` contains only public-safe artifacts (contact cards)
- `private/` contains tenant operational state (config, aliases, contracts metadata, logs)
- `vault/` stores no secrets in repo; only documents KeePass usage
- `data/` contains caches and derived/generated artifacts; not public by default

---

## 1) `app.py` — root router and boundary enforcement

**Purpose**
- Own the namespace separation: `/`, `/portal/**`, `/api/**`.
- Serve templates/static for the portal UI.
- Wire feature modules (inbox/contracts/magnetlinks/etc.) without turning into a monolith.

**Must implement**
1. **Public contact card route**
   - `GET /<msn_id>.json` returns a *limited* contact card from `public/<msn_id>.json` (or a generated equivalent).
   - Only `options_public` is exposed here.
   - Nothing from `private/` is directly served.

2. **Portal UI routing**
   - `GET /portal` renders `home.html` via `render_template`.
   - Portal static assets served at `/portal/static/*`.

3. **Portal-only API wiring (local dev open; auth later)**
   - Register:
     - `portal/api/inbox.py` → `/portal/api/inbox`
     - `portal/api/contracts.py` → `/portal/api/contracts`
     - `portal/api/magnetlinks.py` → `/portal/api/magnetlinks`
     - `portal/api/config.py` and `portal/api/aliases.py` if you modularize those routes
   - Add a portal gate hook:
     - Today: `AUTH_MODE=none` lets everything through
     - Later: protect all `/portal/**` at NGINX/Keycloak or in-app JWT verify.

4. **Externally callable signed API wiring**
   - Register `portal/api/public_inbox.py` → `/api/inbox/<msn_id>`
   - This endpoint is **not** in `/portal/**` and does **not** rely on Keycloak.
   - It relies on request signing verification.

**Outputs**
- A single running server with correct path boundaries.
- No accidental exposure of private data.

---

## 2) `portal/services/policy.py` — centralized boundary rules

**Purpose**
- Avoid scattering security decisions across files.

**Must implement**
- Constants/functions describing:
  - what is considered “public”
  - what is considered “portal-only”
  - what is considered “external signed”
- Helpers such as:
  - `is_public_path(path) -> bool`
  - `is_portal_path(path) -> bool`
  - `is_external_signed_path(path) -> bool`

**Outputs**
- A single source of truth used by `app.py` (and optionally in request verification).

---

## 3) NDJSON operational storage (request log)

### 3.1 `portal/services/request_log_store.py` (already exists)

**Purpose**
- Append-only, durable operational event log.

**Must implement**
- `append_event(private_dir, msn_id, event) -> Path`
  - Adds `ts_unix_ms` and `msn_id` if missing.
  - Writes one JSON object per line (NDJSON).
  - Rejects/avoids secrets.

- `read_events(private_dir, msn_id, limit, offset, reverse) -> ReadResult`
  - Returns events + basic metadata about parse errors and totals.

**Outputs**
- `private/request_log/<msn_id>.ndjson` stores portal events.

### 3.2 `private/request_log/README.md` (already exists)

**Purpose**
- Human-facing rules for what goes into the request log.

**Must include**
- NDJSON format
- no-secrets policy
- example lines
- rotation guidance (future)

---

## 4) Portal-only inbox API (home portal uses this)

### `portal/api/inbox.py` (already exists)

**Purpose**
- Provide read/write access to NDJSON request logs to the portal UI.

**Must implement**
- `GET /portal/api/inbox?msn_id=...&limit=&offset=&reverse=`
  - Reads NDJSON via `request_log_store.read_events`.
- `POST /portal/api/inbox?msn_id=...` (local dev convenience)
  - Appends event to NDJSON via `append_event`.
  - Reject obvious secret keys.
- `OPTIONS` handlers.

**Outputs**
- Portal can display operational events on the Home page.

**Note**
- Long term, you likely disable `POST /portal/api/inbox` in production and accept inbound events via signed external endpoints only.

---

## 5) Contact cache for sender key resolution

### `portal/services/contact_cache.py` (to be created)

**Purpose**
- Resolve public keys and metadata for inbound signed requests without requiring schema work.

**Storage**
- `data/cache/contacts/<sender_msn_id>.json` (cached copy of `GET /<sender_msn_id>.json`)
- Include a cache timestamp (e.g., `cached_unix_ms`).

**Must implement**
- `get_cached(sender_msn_id) -> dict|None`
- `put_cached(sender_msn_id, contact_card_dict) -> Path`
- `is_stale(contact_card_dict, ttl_seconds) -> bool`
- Optional:
  - `resolve(sender_msn_id, fetch_fn) -> dict` which:
    1) returns cached if fresh
    2) else fetches remote contact card (server-side HTTP), caches it, returns it

**Outputs**
- Any inbound request path can quickly look up the sender’s public key.

---

## 6) Signature verification (authentication + integrity)

### `portal/services/crypto_signatures.py` (to be created)

**Purpose**
- Verify **signed** requests using sender public keys (asymmetric).
- Later support HMAC verification (symmetric) for contract-authenticated calls.

**Must implement (phase 1)**
- A canonicalization routine that builds the bytes to verify:
  - method, path, query
  - hash(body)
  - timestamp + nonce headers
  - host header

- `verify_signed_request(request, sender_public_key) -> bool`
  - Phase 1 can be a stub that returns False unless a debug flag is set.
  - Phase 2 implements Ed25519 verification (recommended).

**Must implement (phase 2)**
- `verify_hmac_request(request, shared_secret) -> bool`
  - Used when contract exists and symmetric key is available via `key_ref`.

**Outputs**
- A single verification API used by `public_inbox.py` and other external signed endpoints.

---

## 7) External signed inbox endpoint (the “inbound message” path)

### `portal/api/public_inbox.py` (to be created)

**Purpose**
- Allow outsiders to deliver a message/request to a portal without portal login.
- Enforces signing verification.
- Appends a sanitized event to `private/request_log/<msn_id>.ndjson`.

**Route**
- `POST /api/inbox/<msn_id>`

**Inputs**
- Headers (example):
  - `X-MyCite-From` (sender msn_id)
  - `X-MyCite-KeyId` (optional; helps key selection)
  - `X-MyCite-Timestamp`
  - `X-MyCite-Nonce`
  - `X-MyCite-Signature`

- Body:
  - JSON message payload (no secrets; if secrets are required later, use hybrid encryption with an envelope)

**Processing logic**
1. Identify `target_msn_id` from path parameter.
2. Identify `sender_msn_id` from header.
3. Resolve sender contact card via `contact_cache` (or fetch+cache).
4. Verify signature via `crypto_signatures`.
5. Append event to NDJSON via `request_log_store.append_event`:
   - `type: "request.received"`
   - `from_msn_id: sender_msn_id`
   - `auth: "signed"`
   - `status: "pending"`
   - `details: { ...sanitized summary... }`
6. Return 202 Accepted with an event id or timestamp.

**Outputs**
- Real inbound request flow exists without Keycloak.

---

## 8) Contracts: metadata store + portal-only API

### 8.1 `portal/services/contract_store.py` (to be created)

**Purpose**
- Manage contract metadata lifecycle (no secrets).

**Storage**
- `private/contracts/contract-<contract_id>.json`

**Contract lifecycle fields (minimum)**
- `contract_id` (opaque id)
- `contract_type` (e.g., `"magnetlink"`, `"service"`, `"alias"`, etc.)
- `counterparty_msn_id`
- `status`: `pending|active|revoked|expired`
- `created_unix_ms`, `updated_unix_ms`
- `key_ref` references (no key material)

**Must implement**
- `list_contracts(filter_type=None) -> list`
- `get_contract(contract_id) -> dict`
- `create_contract(metadata) -> contract_id`
- `update_contract(contract_id, patch) -> dict` (or overwrite)
- Basic validations: reject secret-bearing keys.

**Outputs**
- A consistent file-backed lifecycle store.

### 8.2 `portal/api/contracts.py` (already generated; wire it)

**Purpose**
- Portal-only management UI endpoints for contract metadata.

**Must implement**
- List contracts (with filtering by `contract_type`)
- Read contract
- Create contract
- (Optional later) update/revoke

**Outputs**
- Portal home tools can display contracts and allow acceptance/revocation.

---

## 9) Magnet-links: “contracts with standard operations”

### `portal/api/magnetlinks.py` (already generated; wire it)

**Purpose**
- Treat magnet-links as contracts with `contract_type="magnetlink"`.
- Provide standard local operations:
  - list magnet-links
  - create magnet-link metadata
  - check/update marker (e.g., `last_checked_unix_ms`)

**Must implement**
- `GET /portal/api/magnetlinks?msn_id=...`
- `POST /portal/api/magnetlinks?msn_id=...` (creates magnetlink contract metadata)
- `POST /portal/api/magnetlinks/check?msn_id=...` (updates marker; later becomes a network poll)

**Outputs**
- A stable operational interface for update-checking without introducing package staging.

---

## 10) Tools UI placeholders (no tool logic yet)

### UI files (already created)
- `portal/ui/templates/base.html`
- `portal/ui/templates/home.html`
- `portal/ui/templates/alias_shell.html`
- `portal/ui/static/portal.css`
- `portal/ui/static/portal.js`

**Purpose**
- Provide the portal shell:
  - left alias sidebar always visible
  - home view has tabs
  - alias session view hides tabs and shows an org widget placeholder

**Must implement now**
- Nothing more than rendering.
- Tools remain placeholders; they can later call portal APIs.

**Outputs**
- A stable UX frame to hang features on.

---

## 11) Wiring checklist (what “done” looks like)

You are done with the MVP implementation when:

1. `GET /<msn_id>.json` works and returns *only* public-safe fields.
2. `GET /portal` renders `home.html` and loads `portal.css`/`portal.js`.
3. `GET /portal/api/inbox?msn_id=...` returns NDJSON events (empty is fine).
4. `POST /api/inbox/<msn_id>`:
   - verifies a signature (stub is fine if explicitly flagged)
   - appends `request.received` event to NDJSON.
5. `GET /portal/api/contracts?msn_id=...` lists contract metadata files.
6. `GET /portal/api/magnetlinks?msn_id=...` lists `contract_type="magnetlink"` contracts.
7. Nothing in `private/` is ever served directly by path (only via API).

---

## 12) Explicit non-goals (for now)

- No schema formalization beyond consistent key names and file placement.
- No Keycloak enforcement yet (paths are ready; auth can be added later).
- No staging/installation pipeline for “packages”.
- No secrets stored in JSON files; only `key_ref`.

# request_log_and_contracts.md

## Objective

Flesh out the **request log + contracts** path so that two portals can:

1. **Initiate contact** (discover and message another portal).
2. **Propose a contract** and log the full lifecycle in `private/request_log/*.ndjson`.
3. **Accept/decline in the background** (later surfaced in the portal UI), and respond to establish mutual state with the counterparty.
4. After an **active contract** exists, enable creating and using **aliases** and **progeny**, including an **optional progeny UI** directory layout.

This document is **portal-agnostic** (applies to NE and LE portals).

---

## Invariants to preserve

### Namespaces

- **Public (anonymous):** `GET /<msn_id>.json`
- **Portal-only (auth later):** `/portal/**`
- **Externally callable but signed (no portal session):** `/api/**`

### Data boundaries

- `public/` = public-safe contact cards only  
- `private/` = operational state (config, aliases, contracts metadata, logs)  
- `vault/` = key material references and operator docs (do not commit secrets)  
- `data/` = caches + derived artifacts (not public by default)

---

## Canonical stores

### Request log (NDJSON)

- File: `private/request_log/<msn_id>.ndjson`
- Append-only. One JSON object per line.
- Contains operational events (sent/received messages, contract lifecycle, alias/progeny creation).

### Contract metadata (JSON)

- File: `private/contracts/contract-<contract_id>.json`
- No secrets (store only refs like `key_ref` / `key_id`).
- `status`: `pending | active | revoked | expired`

---

## Phase plan

### Phase 0 — Make every portal “contract-capable”

**Goal:** any portal that participates in cooperation must implement the same minimum capability set as the reference portal:

- `/<msn_id>.json` public contact card
- `/portal/api/inbox` (read/write request log)
- `/portal/api/contracts` (create/list/get contract metadata)
- `/api/inbox/<msn_id>` (external signed inbound path that logs to request log)
- `portal/services/contact_cache.py` for resolving sender contact cards/keys

**Action:** port the working modules into other portals (LE and NE).

```bash
# run from: ~/dev/flaskmycite
cd ~/dev/flaskmycite
rsync -av mycite-ne_mw/portal/api/ mycite-le_fnd/portal/api/
rsync -av mycite-ne_mw/portal/services/ mycite-le_fnd/portal/services/
```

> For LE portals, keep `/portal/embed/poc` as-is, but still add the APIs above.

**Deliverable check:** for each portal, these endpoints must return 200/4xx appropriately:

```bash
# run from anywhere
curl -i "http://127.0.0.1:<PORT>/<MSN_ID>.json"
curl -i "http://127.0.0.1:<PORT>/portal/api/inbox?msn_id=<MSN_ID>"
curl -i "http://127.0.0.1:<PORT>/portal/api/contracts?msn_id=<MSN_ID>"
```

---

### Phase 1 — Initiate contact (discovery + first message)

**Goal:** Portal A discovers Portal B and sends a first message.

#### 1.1 Normalize the public contact card

Public card must remain minimal, but include enough to authenticate and route:

- `msn_id`, `title`, `entity_type`
- `public_key` (or `public_keys` later)
- optional `accessible` identifiers (e.g., `msn_index` pointer)
- `options_public.self`

#### 1.2 Implement an outbound message client (server-side)

Add:

- `portal/services/outbound_requests.py`
  - `fetch_contact_card(msn_id) -> dict`
  - `post_signed_inbox(target_base_url, target_msn_id, sender_msn_id, body) -> (status, json)`
  - `append_outbound_event(private_dir, msn_id, event)` (or reuse request_log_store directly)

Create the file:

```bash
# run from: ~/dev/flaskmycite/<portal_dir>
cd ~/dev/flaskmycite/<portal_dir>
mkdir -p portal/services
touch portal/services/outbound_requests.py
```

**Logging rule:**
- On send → append `request.sent`
- On receive → append `request.received` (already done by inbound path)

---

### Phase 2 — Contract offer as an inbox message

**Goal:** propose a contract by delivering a structured message to the counterparty’s external inbox:

- `POST /api/inbox/<target_msn_id>`

This avoids adding new endpoints, and gives you a single external “message ingress” surface.

#### 2.1 Define the message schema (contract offer)

Example body JSON:

```json
{
  "schema": "mycite.message.v0",
  "type": "contract.offer",
  "msg_id": "optional-stable-id",
  "contract": {
    "contract_id": "",
    "contract_type": "symmetric_key",
    "initiator_msn_id": "A",
    "counterparty_msn_id": "B",
    "capabilities": ["hmac_inbox", "alias_session", "progeny_invite"],
    "key_exchange": {
      "mode": "hmac",
      "key_ref_proposal": "vault_ref_only"
    }
  }
}
```

Rules:
- No raw secrets.
- Contract ID can be initiator-generated or receiver-generated; pick one convention and keep it stable.
- Prefer a stable `msg_id` for idempotency.

#### 2.2 Sender workflow (Portal A)

1. Create local contract metadata with `status="pending"`.
2. Log `contract.offer.created`.
3. Send `contract.offer` message to Portal B.
4. Log `contract.offer.sent` with response status.

Create contract metadata via portal API (dev convenience):

```bash
# run from anywhere
curl -sS -X POST "http://127.0.0.1:<A_PORT>/portal/api/contracts?msn_id=<A_MSN_ID>" \
  -H "Content-Type: application/json" \
  -d '{"contract_type":"symmetric_key","counterparty_msn_id":"<B_MSN_ID>","status":"pending"}' | jq
```

Then send the offer via the external inbox:

```bash
# run from anywhere
curl -sS -X POST "http://127.0.0.1:<B_PORT>/api/inbox/<B_MSN_ID>" \
  -H "Content-Type: application/json" \
  -H "X-MyCite-From: <A_MSN_ID>" \
  -H "X-MyCite-Timestamp: 0" \
  -H "X-MyCite-Nonce: dev" \
  -H "X-MyCite-Signature: dev" \
  -d '{"schema":"mycite.message.v0","type":"contract.offer","msg_id":"dev-1","contract":{"contract_type":"symmetric_key","initiator_msn_id":"<A_MSN_ID>","counterparty_msn_id":"<B_MSN_ID>","capabilities":["hmac_inbox","alias_session"]}}' | jq
```

#### 2.3 Receiver workflow (Portal B)

Inbound path currently logs only a **summary** of payload keys/size. That is **insufficient** for contract processing.

**Required change:** if inbound body has `type == "contract.offer"`:

- store a sanitized copy in `data/queue/inbox/<event_id>.json`
- log `contract.offer.received` with `payload_ref`
- store a stable `event_id` (or use the NDJSON line index + timestamp)

Create the queue dir:

```bash
# run from: ~/dev/flaskmycite/<portal_B_dir>
cd ~/dev/flaskmycite/<portal_B_dir>
mkdir -p data/queue/inbox
```

Sanitization rule:
- reject forbidden secret keys (keep the existing “no secrets” policy)
- if you later need secret-bearing payloads, use envelope encryption and store only ciphertext + metadata

---

### Phase 3 — Background acceptance processor (“contract daemon”)

**Goal:** Portal B can accept/decline offers automatically or semi-automatically, without blocking on UI.

Add:

- `portal/services/contract_daemon.py`
  - reads request log incrementally
  - finds unprocessed `contract.offer.received`
  - applies policy (allowlist + contract_type rules)
  - if accepted:
    - create/update `private/contracts/contract-<id>.json` → `status="active"`
    - send `contract.accept` message back to Portal A
    - log `contract.accept.sent`
  - if declined:
    - mark contract `revoked` (or add `declined`)
    - send `contract.decline`
    - log `contract.decline.sent`

#### 3.1 Idempotency checkpoint

Add:

- `private/daemon_state/contract_daemon.json` with `last_processed_line`

```bash
# run from: ~/dev/flaskmycite/<portal_B_dir>
cd ~/dev/flaskmycite/<portal_B_dir>
mkdir -p private/daemon_state
printf '{\n  "last_processed_line": 0\n}\n' > private/daemon_state/contract_daemon.json
```

#### 3.2 Config policy keys (for later UI control)

In `private/mycite-config-<msn_id>.json` add:

- `contract_policy.allow_counterparties`: allowlist of MSN IDs
- `contract_policy.auto_accept_types`: list of contract types allowed to auto-accept
- `contract_policy.require_manual_accept`: `true|false`
- `contract_policy.default_response`: `"accept" | "decline"` (optional)

These are **not secrets**, so they can live in config.

#### 3.3 Run daemon (dev)

```bash
# run from: ~/dev/flaskmycite/<portal_B_dir>
cd ~/dev/flaskmycite/<portal_B_dir>
source .venv/bin/activate
python -m portal.services.contract_daemon --once --msn-id "<B_MSN_ID>"
```

**UI integration later (critical separation of concerns):**
- UI toggles policy flags and/or approves specific pending offers
- daemon performs network side effects and writes all log entries

---

### Phase 4 — Sender activates contract on acceptance

Acceptance payload example:

```json
{
  "schema": "mycite.message.v0",
  "type": "contract.accept",
  "msg_id": "optional-stable-id",
  "contract": {
    "contract_id": "<contract_id>",
    "contract_type": "symmetric_key",
    "initiator_msn_id": "A",
    "counterparty_msn_id": "B",
    "status": "active",
    "key_exchange": {
      "mode": "hmac",
      "key_ref_confirmed": "vault_ref_only"
    }
  }
}
```

Sender processing (Portal A):

- log `contract.accept.received` with `payload_ref`
- update local contract metadata to `status="active"`
- log `contract.activated`

Implement this either:
- inside the same daemon (processing inbound events), or
- in a second “inbox processor” daemon.

---

### Phase 5 — Use contracts to authenticate future calls

**Goal:** after activation, allow contract-authenticated requests.

Recommended headers:

- `X-MyCite-Contract: <contract_id>`
- `X-MyCite-Signature: <base64 HMAC over canonical request bytes>`

Inbound behavior:

1. Lookup contract metadata by `contract_id`
2. Resolve key material via `key_ref` from `vault/` (do not commit secrets)
3. Verify HMAC

Dev shortcut (keep your current “insecure signatures allowed” flag):

```bash
# run from: ~/dev/flaskmycite/<portal_dir>
cd ~/dev/flaskmycite/<portal_dir>
export MYCITE_ALLOW_INSECURE_SIGNATURES=1
python app.py
```

---

### Phase 6 — After contract is active: create aliases and progeny

Once a contract is active, you can allow “relationship state” to be created.

#### 6.1 Alias creation

**Alias storage**
- Directory: `private/aliases/`
- Convention: `alias-<natural_msn_id>-to-<host_msn_id>-<role>.json`

Minimum fields:
- `msn_id` (NE msn)
- `alias_host` (host portal msn)
- `host_title`
- `role`
- `symmetric_key_contract` (contract reference)

Create directory:

```bash
# run from: ~/dev/flaskmycite/<portal_dir>
cd ~/dev/flaskmycite/<portal_dir>
mkdir -p private/aliases
```

Log events:
- `alias.created`
- `alias.updated`

#### 6.2 Progeny creation

Progeny is subordinate records owned by a portal (LE or NE), grouped by **type**.

---

## Optional progeny UI + directory layout

### Templates and static

Under a portal:

- `portal/ui/templates/progeny/<type>/index.html`
- `portal/ui/templates/progeny/<type>/detail.html`
- `portal/ui/static/progeny/<type>/...` (optional)

Create example type dirs:

```bash
# run from: ~/dev/flaskmycite/<portal_dir>
cd ~/dev/flaskmycite/<portal_dir>
mkdir -p portal/ui/templates/progeny/poc
mkdir -p portal/ui/templates/progeny/board_member
mkdir -p portal/ui/templates/progeny/tenant
mkdir -p portal/ui/static/progeny/poc
mkdir -p portal/ui/static/progeny/board_member
mkdir -p portal/ui/static/progeny/tenant
```

### Progeny JSON storage

- `private/progeny/<type>/progeny-<parent_msn_id>-<child_msn_id>-<type>.json`

Create progeny dirs:

```bash
# run from: ~/dev/flaskmycite/<portal_dir>
cd ~/dev/flaskmycite/<portal_dir>
mkdir -p private/progeny/poc
mkdir -p private/progeny/board_member
mkdir -p private/progeny/tenant
mkdir -p private/progeny/tool
```

### Progeny JSON minimum schema

```json
{
  "schema": "mycite.progeny.v0",
  "parent_msn_id": "<owner_msn_id>",
  "child_msn_id": "<child_msn_id_or_identifier>",
  "progeny_type": "poc",
  "status": "active",
  "created_unix_ms": 0,
  "updated_unix_ms": 0,
  "display": {
    "title": "Human readable label",
    "role_title": "Point of Contact"
  },
  "links": {
    "public_contact_card": "/<child_msn_id>.json"
  },
  "contracts": {
    "control_contract_id": "<optional>"
  }
}
```

### Progeny index in config (avoid blind filesystem scans)

Add to `private/mycite-config-<msn_id>.json`:

```json
{
  "progeny_index": {
    "poc": ["progeny-<parent>-<child>-poc.json"],
    "tenant": ["..."]
  }
}
```

---

## Request log event taxonomy (recommended)

### Contract events

- `contract.offer.created`
- `contract.offer.sent`
- `contract.offer.received`
- `contract.accept.sent`
- `contract.accept.received`
- `contract.decline.sent`
- `contract.decline.received`
- `contract.activated`
- `contract.revoked`

### Relationship events

- `alias.created`
- `alias.updated`
- `progeny.created`
- `progeny.updated`

### Generic request events

- `request.sent`
- `request.received`

Each event should include:
- `ts_unix_ms`
- `msn_id` (local)
- `from_msn_id` / `to_msn_id` as applicable
- `contract_id` as applicable
- `payload_ref` when persisted to `data/queue/...`

---

## Minimal smoke test sequence

Assume:
- Portal A on `127.0.0.1:5000`
- Portal B on `127.0.0.1:5001`

### 1) Verify public cards

```bash
# run from anywhere
curl -sS "http://127.0.0.1:5000/<A_MSN_ID>.json" | jq
curl -sS "http://127.0.0.1:5001/<B_MSN_ID>.json" | jq
```

### 2) Send contract offer message (dev signing stub)

```bash
# run from anywhere
curl -sS -X POST "http://127.0.0.1:5001/api/inbox/<B_MSN_ID>" \
  -H "Content-Type: application/json" \
  -H "X-MyCite-From: <A_MSN_ID>" \
  -H "X-MyCite-Timestamp: 0" \
  -H "X-MyCite-Nonce: dev" \
  -H "X-MyCite-Signature: dev" \
  -d '{"schema":"mycite.message.v0","type":"contract.offer","contract":{"contract_type":"symmetric_key","initiator_msn_id":"<A_MSN_ID>","counterparty_msn_id":"<B_MSN_ID>","capabilities":["hmac_inbox","alias_session"]}}' | jq
```

### 3) Inspect request log

```bash
# run from: ~/dev/flaskmycite/<portal_B_dir>
cd ~/dev/flaskmycite/<portal_B_dir>
tail -n 50 private/request_log/<B_MSN_ID>.ndjson
```

---

## Key gaps this plan closes

- LE portals currently lack request log + contracts + external inbox → Phase 0 fixes parity.
- Contract offers aren’t persistable for later processing → Phase 2.3 adds payload refs.
- No background “accept/respond” mechanism exists → Phase 3 adds daemon + policy.
- Contract-authenticated calls aren’t enforceable → Phase 5 introduces HMAC path.
- Progeny isn’t first-class in UI/storage → Phase 6 adds optional directories + JSON schema.

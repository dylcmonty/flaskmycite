# MyCite Portal Prototype

This repository defines a **single portal codebase** that operates over an entity’s on-disk state.
The state model supports:
- **Natural entities** (a human operator’s “president view” in the portal), and
- **Legal entities** (organizations), whose operational state can be hosted and operated by a natural entity.

The system is **path-boundary driven**: what is public, what is portal-only, and what is externally callable is determined by URL namespaces and by which state root is active.

---

## Core invariants

### HTTP surface invariants
- **Public (anonymous):** `GET /<msn_id>.json` only.
- **Portal-only (interactive UI + internal control-plane APIs):** `/portal/**`.
- **Externally callable (machine-to-machine):** `/api/**`.
  - This namespace is intended for **signed** requests and does **not** rely on portal login.

### Secret handling invariants
- **No secrets** are stored in repo-tracked JSON files.
- Secret material (private keys, symmetric contract keys, tokens) lives in a vault (KeePass `.kdbx`) and is referenced via `key_ref`.
- Public keys may appear in public contact cards.

See `vault/README.md`.

### Operational storage invariants
- Request/event logging is **append-only NDJSON** under `private/request_log/`.
- Contract records are **metadata-only JSON** under `private/contracts/` (no secrets).
- Alias records are **portal-only JSON** under `private/aliases/`.

See `private/request_log/README.md`.

---

## Concepts (no schema enforcement)

MyCite does not assume a formal schema engine at this stage; it relies on consistent conventions.

### Entity identity
- Every entity has an `msn_id`.
- The public contact card is `public/<msn_id>.json` and is served at `GET /<msn_id>.json`.

### President view vs POC view
These are UI contexts in the portal:
- **President view:** the portal home view for the operating natural entity.
- **POC view:** an alias-session view into a legal entity context (the operator acting “as POC” with respect to that organization).

Both are operated by the same portal UI; authorization to enter an org context is an integration concern (auth system), not a separate login model.

### Progeny and aliases (legal entity rule)
- Legal entities define **progeny types** in their private config (e.g., `poc`, `tenant`, `board_member`).
- An **alias session** is valid only if it corresponds to an organization-defined progeny type and instance rules.
- Alias JSON structure is intended to be defined by the organization (via progeny/interface templates), while the portal stores instances as private records.

### Contracts and magnet-links
- A **contract** is a portal-private record that binds two `msn_id`s with permissions and key references (`key_ref`).
- A **magnet-link** is a specific kind of contract with standardized operations (check, read, request updates).
- “Packages/tools/data” do not assume responsibility for updating themselves; update behavior is defined and driven via magnet-link operations and contracts.

---

## Repository layout

```text
mycite/
  app.py                          # HTTP routing + module wiring

  portal/
    ui/                           # portal shell UI
      templates/                  # base.html, home.html, alias_shell.html, etc.
      static/                     # portal.css, portal.js
    api/                          # portal-only JSON APIs (registered by app.py)
    tools/                        # optional portal tools (conventions only)

  public/                         # public-safe artifacts (anonymous fetch)
    <msn_id>.json

  private/                        # portal-only operational state
    mycite-config-<msn_id>.json
    aliases/
      alias-*.json
    contracts/
      contract-<id>.json
    request_log/
      <msn_id>.ndjson

  data/                           # caches + derived artifacts (not public by default)
    cache/
    artifacts/

  vault/                          # vault conventions (no secrets committed)
```

---

## Implemented UI surfaces

- `GET /portal`
  - Portal shell
  - Left sidebar: alias selection
  - Home view: top tabs (tools may remain placeholders)
- Alias session pages are rendered by templates but the organization “widget view” is an explicit integration boundary.

---

## Implemented API surfaces (portal-only)

These endpoints are intended to be accessed through the portal UI context:
- `GET /portal/api/config?msn_id=...`
- `GET /portal/api/aliases?msn_id=...`
- `GET /portal/api/inbox?msn_id=...` (NDJSON-backed event feed)

Other portal APIs (contracts/magnetlinks) may be present depending on wiring in `app.py`.

---

## External machine-to-machine namespace

`/api/**` is reserved for externally callable requests (e.g., signed inbound messages).
These endpoints are designed to:
- verify signatures using sender public keys resolved from contact cards/caches, and
- append operational events to NDJSON logs, and/or propose contracts.

This namespace must remain distinct from `/portal/**` so portal authentication can be enforced without opening holes for outsiders.

---

## Running the portal

```bash
# run from: ~/dev/mycite
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Open in a browser:
- `http://127.0.0.1:5000/portal`

Verify static assets:
```bash
# run from: ~/dev/mycite
curl -I http://127.0.0.1:5000/portal/static/portal.css
curl -I http://127.0.0.1:5000/portal/static/portal.js
```

---

## Copying this codebase to operate separate entity state

This codebase is intended to be reusable across multiple entity state roots (natural and legal entities).
The mechanism for selecting the active state root (president vs hosted org context) is a portal/session integration concern; the state layout conventions above remain the same regardless of hosting strategy.

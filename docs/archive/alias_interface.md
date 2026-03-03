# alias_interface.md

This document defines the **minimum viable “alias interface” implementation** in the current two-repo setup:

- `mycite-ne/` = **natural entity** portal (user portal; “president view”)
- `mycite-le/` = **legal entity** portal (organization portal; “org widget” provider)

Goal: In `mycite-ne`, selecting an alias from the left sidebar renders an **alias session page**
that shows:
1) an alias profile summary (portal-owned representation), and
2) an **embedded organization widget** served by `mycite-le` (placeholder widget for now).

This is written as **hard facts** for Codex: file-by-file, in build order.

---

## 0) Invariants (do not break)

### URL boundaries
- Public remains only: `GET /<msn_id>.json`
- Portal UI + internal APIs: `/portal/**`
- External signed APIs (later): `/api/**`

### Separation of concerns
- `mycite-ne` does not copy organization UI code.
- `mycite-le` provides an **embed view** (widget) that can be loaded from `mycite-ne`.

### No auth implementation in this task
Assume access is correct during development. Do not implement Keycloak wiring here.

---

## 1) `mycite-ne`: add alias-session route and template render

### 1.1 Modify `mycite-ne/app.py`
**Purpose**
- Add a new UI route:
  - `GET /portal/alias/<alias_id>`
- Load alias records from `mycite-ne/private/aliases/`.
- Render `portal/ui/templates/alias_shell.html` with template context:
  - sidebar aliases list
  - active alias info
  - org widget URL (points to `mycite-le`)

**Requirements**
- Must not serve private files directly.
- Must not accept filesystem paths from the request (alias_id is an identifier, not a path).

**Implementation sketch**
1) Implement a helper function:
   - `list_aliases_ne(private_dir) -> list[dict]`
     - returns list of aliases for sidebar with fields:
       - `alias_id`: stable id (recommended: filename stem without extension)
       - `label`: display label (recommended: `given_name family_name` or `host_title`)
       - `org_title`: optional display subtitle
       - `org_msn_id`: organization msn_id (recommended: `alias_host` field in alias JSON)

2) Implement a helper function:
   - `load_alias_ne(private_dir, alias_id) -> dict`
     - resolves alias_id to a file in `private/aliases/` (exact match by stem)
     - reads JSON

3) Add route:
   - `@app.get("/portal/alias/<alias_id>")`
     - loads aliases list
     - loads selected alias
     - derives:
       - `org_msn_id` from alias record (e.g., `alias_host`)
       - `org_title` from alias record (e.g., `host_title`)
     - builds widget URL:
       - default dev URL: `http://127.0.0.1:5001/portal/embed/poc`
       - include query params:
         - `org_msn_id=<org_msn_id>`
         - `as_alias_id=<alias_id>`
     - renders `alias_shell.html`

**Outputs**
- `mycite-ne` can render alias sessions as separate pages without home tabs.

---

## 2) `mycite-ne`: update `portal/ui/templates/alias_shell.html` to support a real widget URL

### Modify `mycite-ne/portal/ui/templates/alias_shell.html`
**Purpose**
- Replace the current static “org widget placeholder” block with:
  - an iframe container that loads the organization widget URL.

**Requirements**
- Do not implement cross-origin JavaScript communication at this stage.
- Keep the widget boundary “opaque” (implementation remains ambiguous).

**Template context required**
- `org_widget_url` (string)
- `org_title` (optional)
- `org_msn_id` (string)
- `active_alias_id` (string)
- `alias_label` (string)
- `aliases` list for sidebar

**Minimum HTML change**
- In the widget panel, render:
  - `<iframe src="{{ org_widget_url }}" ...></iframe>`
- Provide a fallback message if `org_widget_url` is missing.

**Outputs**
- Alias session view shows alias profile + embedded organization widget.

---

## 3) `mycite-ne`: optional CSS and JS adjustments (no new behavior required)

### 3.1 `mycite-ne/portal/ui/static/portal.css`
**Purpose**
- Ensure the iframe widget fills the right panel area cleanly.

**Minimum changes**
- Add a rule to make iframe responsive:
  - width: 100%
  - min-height: 520px (or 100% of container)
  - border: 0
  - background: transparent

### 3.2 `mycite-ne/portal/ui/static/portal.js`
**Purpose**
- No required changes for alias navigation.
- Keep home tab switching and sidebar alias filtering.

**Outputs**
- Cosmetic + layout stability only.

---

## 4) `mycite-le`: add the minimal embedded widget view

### 4.1 Modify `mycite-le/app.py`
**Purpose**
- Provide a simple embed endpoint that can be loaded from `mycite-ne`:

  - `GET /portal/embed/poc`

**Requirements**
- The response must NOT include the full portal shell (no sidebar, no tabs).
- The response must be safe to render inside an iframe.

**Implementation sketch**
- Route reads query params:
  - `org_msn_id` (optional; for display)
  - `as_alias_id` (optional; for display)
- Render `portal/ui/templates/embed_poc.html`
- Pass template context:
  - `org_msn_id`, `as_alias_id`, `org_title` if available

**Outputs**
- `mycite-le` provides a widget placeholder that represents “organization session view.”

---

## 5) `mycite-le`: create `portal/ui/templates/embed_poc.html`

### Create `mycite-le/portal/ui/templates/embed_poc.html`
**Purpose**
- Minimal “organization session” widget that can later be replaced by org-defined view logic.

**Must include**
- A compact header:
  - org_msn_id, alias_id
- A placeholder body:
  - “This is the organization widget surface.”
  - “Later this will render org-defined session views.”

**Must NOT include**
- portal sidebar
- home tabs
- navigation shell

**Outputs**
- A stable embed surface to build on.

---

## 6) Local dev run configuration

### Ports
To avoid collisions:
- `mycite-ne` runs on `127.0.0.1:5000`
- `mycite-le` runs on `127.0.0.1:5001`

If `mycite-le` currently runs on 5000, change its `app.run(... port=5001 ...)`.

---

## 7) Smoke tests (hard checks)

### 7.1 Start both servers

```bash
# terminal A (mycite-ne)
cd ~/dev/mycite-ne
source .venv/bin/activate
python app.py
```

```bash
# terminal B (mycite-le)
cd ~/dev/mycite-le
source .venv/bin/activate
python app.py
```

### 7.2 Verify home portal renders (NE)
- `http://127.0.0.1:5000/portal`

### 7.3 Verify alias session renders (NE)
- `http://127.0.0.1:5000/portal/alias/<alias_id>`

Expected:
- sidebar visible
- alias card populated
- iframe loads `mycite-le` widget

### 7.4 Verify widget loads directly (LE)
- `http://127.0.0.1:5001/portal/embed/poc?org_msn_id=<org_msn_id>&as_alias_id=<alias_id>`

### 7.5 Static asset checks (NE)
```bash
curl -I http://127.0.0.1:5000/portal/static/portal.css
curl -I http://127.0.0.1:5000/portal/static/portal.js
```

---

## 8) Explicit non-goals for this task
- No Keycloak integration.
- No signature verification or contract checks.
- No cross-origin messaging between iframe and parent.
- No org-defined UI packages or update mechanisms.
- No schema formalization.

This is purely the minimal alias selection → alias session page → embedded org widget path.

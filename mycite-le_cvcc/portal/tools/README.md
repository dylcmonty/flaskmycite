# portal/tools/

This directory is for **optional home-page tool packages** used by the portal UI.
Tools are not part of the default core behavior; the portal should still work with zero tools installed.

The goal is to keep tool implementation **ambiguous** for now while locking down:
- where tools live
- how the portal can discover them
- what a tool is allowed to do

## Concept
A tool is a Python module that can contribute:
- a home-page tab (UI panel)
- optional portal API handlers (later)
- optional background actions (later)

Tools are different from org-session pages:
- Org-session pages are rendered through the alias session shell and depend on the alias↔org context.
- Tools are portal-local utilities (inbox, contracts view, configuration editor, etc.).

## Minimal structure (recommended)
```text
portal/tools/
  README.md
  __init__.py
  inbox.py           # optional
  contracts.py       # optional
  magnetlinks.py     # optional (UI for magnet-link contracts; core ops live elsewhere)
```

## Discovery (recommended: config-driven)
Keep tools disabled by default. Enable tools via portal/private config.

Example (inside `private/mycite-config-<msn_id>.json`):
```json
{
  "enabled_tools": ["inbox", "contracts", "magnetlinks"]
}
```

Then the portal:
- builds the home-page tabs from `enabled_tools`
- gracefully ignores missing tools (tool not installed)
- never auto-executes arbitrary modules on import (keep imports explicit)

## Tool interface (placeholder)
Do not formalize a schema yet. Use a minimal convention when you’re ready:

- A tool module may expose:
  - `TOOL_ID = "inbox"`
  - `TOOL_TITLE = "Inbox"`
  - `render()` or `get_panel_context()` (later; optional)

For now, it is sufficient that:
- tools exist as modules
- the portal can map `enabled_tools` → a UI tab name
- the actual rendering can remain a stub

## Security and scope
- Tools must never access the vault directly from UI code.
- Any outbound network calls (signed requests) must be executed by backend logic, not by browser JS.
- Tools should write operational events to `private/request_log/<msn_id>.ndjson` or other private stores, not to public files.

## Versioning (future)
If you later want versioned tool payloads, store opaque versions under:
- `data/libs/<tool_name>/<version>/...`

and keep `portal/tools/` as the “active wiring layer” that chooses what to load.

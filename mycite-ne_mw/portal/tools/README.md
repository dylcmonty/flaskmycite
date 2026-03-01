# portal/tools/

This directory defines conventions for **optional portal tools** (home-page utilities).
Tools are not required for the portal shell to run.

## Purpose
Tools may contribute:
- a home-page tab (UI panel)
- optional portal-only API handlers (if explicitly wired)
- optional background actions (if explicitly wired)

Tools do **not** own update logic. Update orchestration is defined by:
- contracts (metadata + key refs), and
- magnet-link operations (standardized check/read/request behavior).

## Discovery model (recommended)
Tools should be enabled explicitly from portal-private configuration, e.g.:

```json
{
  "enabled_tools": ["inbox", "contracts", "magnetlinks"]
}
```

The portal must:
- treat tools as optional,
- degrade gracefully if a tool is missing,
- avoid importing arbitrary modules based on untrusted input.

## Security scope rules
- Tools must never access vault secrets from browser JS.
- Outbound network calls must be performed by backend code.
- Tools should write operational events to NDJSON request logs or other portal-private stores.

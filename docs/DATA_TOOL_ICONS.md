# Data Tool Icons (Presentation Sidecar)

## Intent
Datum icon/title assets are presentation metadata. They do not change anthology semantics, constraints, or table inference.

## Storage

- Global icon library: `/assets/icons/**`
- Per-portal mapping sidecar: `<portal>/data/presentation/datum_icons.json`

Mapping format:

```json
{
  "_meta": {
    "schema": "mycite.presentation.datum_icons.v0",
    "icon_root": "assets/icons"
  },
  "map": {
    "11-0-1": "tables/msn_index.svg",
    "4-1-9": "fields/ascii_field.svg"
  }
}
```

Notes:
- Paths are relative to `assets/icons`.
- SVG source paths are never embedded in anthology JSON.

## Portal endpoints

- `GET /portal/static/icons/<path:relpath>`
  - serves SVG files from `/assets/icons`
  - rejects traversal and non-`.svg` paths
- `GET /portal/api/data/icons/list`
  - returns available icon relpaths for picker UI

## NIMM directive for icon assignment

Use the canonical directive endpoint:

- `POST /portal/api/data/directive`

Request:

```json
{
  "action": "man",
  "subject": "datum_icon",
  "method": "set",
  "args": {
    "datum_id": "11-0-1",
    "icon_relpath": "tables/msn_index.svg"
  }
}
```

Behavior:
- staged into presentation state (`staged_presentation_edits.datum_icons`)
- reflected immediately in returned view models
- persisted to sidecar on `POST /portal/api/data/commit`

Clear mapping:
- same directive with `"icon_relpath": ""`

## View model fields

Datum-oriented payload entries include:
- `datum_id`
- `label_text`
- `icon_relpath`
- `icon_url`
- `icon_assigned`

UI renders these fields only; no direct filesystem scanning in templates.

## Separation of concerns

- Engine (`data/engine/*`): icon mapping semantics, validation, staging, commit.
- Controllers (`portal/api/data_workspace.py` + icon static route): HTTP wiring only.
- UI (`portal/ui/templates/tools/*`, `portal/ui/static/tools/*`): rendering and directive dispatch.

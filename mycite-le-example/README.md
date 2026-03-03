# mycite-le-example

Legal-entity example portal. This directory is the LE reference implementation for organization-facing portal behavior.

## Run locally

```bash
cd mycite-le-example
source .venv/bin/activate
python app.py
```

Default app port in `app.py`: `5001`.

## Implemented capabilities

- Public contact card route: `GET /<msn_id>.json`
- Portal UI shell: `GET /portal`
- Alias session UI: `GET /portal/alias/<alias_id>`
- Embed widget endpoint:
  - `GET /portal/embed/poc`
- Data workspace UI: `GET /portal/data`
- Portal APIs:
  - `/portal/api/config`
  - `/portal/api/aliases`
  - `/portal/api/inbox`
  - `/portal/api/contracts`
  - `/portal/api/magnetlinks`
  - `/portal/api/progeny_config/<progeny_type>`
  - `/portal/api/data/*` (tables, instances, view, stage_edit, revert_edit, reset, commit)
- Signed external inbox surface:
  - `POST /api/inbox/<msn_id>`

Data workspace note:

- If demo data files are absent, `/portal/api/data/tables` returns an empty list and edit actions safely return explicit errors/warnings.

## Canonical docs

- [`../docs/mss_notes.md`](../docs/mss_notes.md)
- [`../docs/request_log_and_contracts.md`](../docs/request_log_and_contracts.md)
- [`../docs/DEVELOPMENT_PLAN.md`](../docs/DEVELOPMENT_PLAN.md)
- [`../docs/DOCUMENTATION_POLICY.md`](../docs/DOCUMENTATION_POLICY.md)
- [`../docs/DATA_TOOL.md`](../docs/DATA_TOOL.md)

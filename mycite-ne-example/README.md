# mycite-ne-example

Natural-entity example portal. This directory is the NE reference implementation for portal shell behavior and API wiring.

## Run locally

```bash
cd mycite-ne-example
source .venv/bin/activate
python app.py
```

Default app port in `app.py`: `5000`.

## Implemented capabilities

- Public contact card route: `GET /<msn_id>.json`
- Portal UI shell: `GET /portal`
- Alias session UI: `GET /portal/alias/<alias_id>`
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

- [`../mss_notes.md`](../mss_notes.md)
- [`../request_log_and_contracts.md`](../request_log_and_contracts.md)
- [`../DEVELOPMENT_PLAN.md`](../DEVELOPMENT_PLAN.md)
- [`../DOCUMENTATION_POLICY.md`](../DOCUMENTATION_POLICY.md)

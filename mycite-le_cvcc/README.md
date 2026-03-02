# mycite-le_cvcc

Client portal instance for CVCC operations.

## Run locally

```bash
cd mycite-le_cvcc
source .venv/bin/activate
python app.py
```

Notes:

- `app.py` default port is `5001`.
- `flask_apps.sh` maps this instance to `5001`.

## Scope

- Active portal app instance with alias-session flow and LE embed surface.
- Board-member community workspace embed (`/portal/embed/board_member`) with Streams, Calendar, People tabs.

## Board Workspace (board_member)

- Workspace files:
  - `private/workspaces/board/v1/streams.ndjson`
  - `private/workspaces/board/v1/calendar.ndjson`
  - `private/workspaces/board/v1/people.json`
- Request-log audit file:
  - `private/request_log/<cvcc_msn_id>.ndjson`
- Example embed URL:
  - `/portal/embed/board_member?member_msn_id=3-2-3-17-77-2-6-4-1-1&as_alias_id=demo-alias&tab=streams`
- Example iframe snippet:

```html
<iframe
  src="http://127.0.0.1:5001/portal/embed/board_member?member_msn_id=3-2-3-17-77-2-6-4-1-1&tab=streams"
  title="CVCC Board Workspace"
  style="width:100%;min-height:640px;border:0;"
></iframe>
```

## Canonical docs

- [`../README.md`](../README.md)
- [`../mss_notes.md`](../mss_notes.md)
- [`../request_log_and_contracts.md`](../request_log_and_contracts.md)
- [`../DEVELOPMENT_PLAN.md`](../DEVELOPMENT_PLAN.md)
- [`../DOCUMENTATION_POLICY.md`](../DOCUMENTATION_POLICY.md)

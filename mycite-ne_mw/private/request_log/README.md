# private/request_log/

This directory holds the portal's **request log** (also referred to as the “inbox”).
It is a portal-only operational store that the portal UI can read to show activity.

## Format: NDJSON (append-only)
Each log is newline-delimited JSON:

- Path: `private/request_log/<msn_id>.ndjson`
- One JSON object per line
- Append-only writes

Reasons for NDJSON:
- trivial to append safely
- human-greppable
- no migrations required
- works without a database

## Content rules (critical)
Do **not** store secret material in request logs:
- no private keys
- no symmetric keys
- no tokens/passwords

Store references and metadata instead (ids, timestamps, counterpart msn_id, status).

## Minimal event fields (recommended)
- `ts_unix_ms`: integer timestamp in milliseconds (added automatically if missing)
- `msn_id`: the local msn_id this log belongs to (added automatically if missing)
- `type`: event type string (e.g., `request.received`, `contract.proposed`, `contract.accepted`)
- `from_msn_id`: requester/counterparty id (if applicable)
- `status`: `pending|accepted|rejected|error` (if applicable)
- `details`: non-secret object payload

Example line:
```json
{"ts_unix_ms":1700000000000,"msn_id":"3-2-...","type":"request.received","from_msn_id":"3-2-...","status":"pending","details":{"note":"wants contract"}}
```

## API usage
Portal-only APIs may expose:
- `GET /portal/api/inbox?msn_id=<msn_id>&limit=...&offset=...&reverse=...`

Externally callable signed APIs (under `/api/**`) may append sanitized events into these logs after verification.

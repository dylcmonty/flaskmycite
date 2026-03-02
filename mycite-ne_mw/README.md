# mycite-ne_mw

Demo/user natural-entity portal instance (MW).

## Run locally

```bash
cd mycite-ne_mw
source .venv/bin/activate
python app.py
```

Notes:

- `app.py` default port is `5000`.
- `flask_apps.sh` maps this instance to `5000`.

## Scope

- Active portal app instance with alias sessions and full NE API stack (config/inbox/contracts/magnetlinks/public inbox).
- Operational docs intentionally retained:
  - `private/request_log/README.md`
  - `vault/README.md`

## Canonical docs

- [`../README.md`](../README.md)
- [`../mss_notes.md`](../mss_notes.md)
- [`../request_log_and_contracts.md`](../request_log_and_contracts.md)
- [`../DEVELOPMENT_PLAN.md`](../DEVELOPMENT_PLAN.md)
- [`../DOCUMENTATION_POLICY.md`](../DOCUMENTATION_POLICY.md)

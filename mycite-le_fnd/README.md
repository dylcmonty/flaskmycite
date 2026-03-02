# mycite-le_fnd

Company portal instance for FND operations.

## Run locally

```bash
cd mycite-le_fnd
source .venv/bin/activate
python app.py
```

Notes:

- `app.py` default port is `5001`.
- `flask_apps.sh` runs this instance on `5002`.

## Scope

- Active portal app instance with company/client pages, alias sessions, embed endpoints, and JSON-backed data tab scaffolding.

## Tenant PayPal Embed (Provider-Held Secrets)

- Tenant embed route:
  - `/portal/embed/tenant?tenant_msn_id=<tenant_msn_id>&contract_id=<contract_id>&as_alias_id=<alias_id>`
- Tab surface in tenant window:
  - Payment Processing (functional)
  - Service Agreement (placeholder)
  - Analytics (placeholder)
  - Blog (placeholder)
- PayPal storage policy:
  - `client_id` is stored in tenant profile JSON
  - `client_secret` is encrypted and stored as ciphertext metadata only
  - no plaintext secrets are written to request logs or profile JSON
- Local key material:
  - generated in `private/vault/contracts/<contract_id>.key`
  - local-only, ignored by git

## Dev-Only Data Experimentation Policy

- FND may host experimental data features under `data/dev/**`.
- Typical examples include prototype lenses, ad-hoc parsers, and temporary recognizers.
- Example portals (`mycite-ne-example`, `mycite-le-example`) remain minimal and stable and must not import FND dev modules.
- A future optional config flag such as `enable_dev_data_features` can be used to gate FND-only experiments.

## Canonical docs

- [`../README.md`](../README.md)
- [`../mss_notes.md`](../mss_notes.md)
- [`../request_log_and_contracts.md`](../request_log_and_contracts.md)
- [`../DEVELOPMENT_PLAN.md`](../DEVELOPMENT_PLAN.md)
- [`../DOCUMENTATION_POLICY.md`](../DOCUMENTATION_POLICY.md)

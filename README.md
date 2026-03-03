# flaskmycite

Repository for MyCite portal prototypes and portal-state instances.

## Repository map

- `mycite-ne-example/`: NE example portal (reference implementation)
- `mycite-le-example/`: LE example portal (reference implementation)
- `mycite-le_fnd/`: company portal instance (FND)
- `mycite-le_cvcc/`: client portal instance (CVCC)
- `mycite-ne_mw/`, `mycite-ne_dm/`: demo/user portal instances
- `mycite-le_tff/`, `mycite-ne_dg/`, `mycite-ne_eb/`, `mycite-ne_jt/`, `mycite-ne_ks/`, `mycite-ne_mt/`: state folders
- `docs/archive/`: historical design notes
- `.flask-multi/`: runtime PID/log artifacts for local launcher scripts

## Canonical docs

- [`docs/mss_notes.md`](docs/mss_notes.md)
- [`docs/request_log_and_contracts.md`](docs/request_log_and_contracts.md)
- [`docs/DEVELOPMENT_PLAN.md`](docs/DEVELOPMENT_PLAN.md)
- [`docs/DOCUMENTATION_POLICY.md`](docs/DOCUMENTATION_POLICY.md)
- [`docs/DATA_TOOL.md`](docs/DATA_TOOL.md)

## Data Architecture

Core data capabilities are separated into three layers:

1. Engine: `<portal>/data/engine/*` (no Flask imports)
2. Controllers: `<portal>/portal/api/data_workspace.py` (thin HTTP glue)
3. UI: tool package + templates/static (`<portal>/portal/tools/data_tool/*`, `<portal>/portal/ui/templates/tools/*`, `<portal>/portal/ui/static/tools/*`)

The Data surface is packaged as a runtime-loaded tool tab:

- Tool route: `/portal/tools/data_tool/home`
- API namespace: `/portal/api/data/*`

Development-only data experiments (extra lenses, ad-hoc recognizers, prototype parsing) are isolated to:

- `mycite-le_fnd/data/dev/*`

## Quick local operations

- Start configured apps: `./flask_apps.sh start`
- Check status: `./flask_apps.sh status`
- Stop apps: `./flask_apps.sh stop`

Current launcher mapping (from `flask_apps.sh`):

- `mycite-ne_mw` -> `127.0.0.1:5000`
- `mycite-le_cvcc` -> `127.0.0.1:5001`
- `mycite-le_fnd` -> `127.0.0.1:5002`

App-local defaults in each `app.py` may differ from launcher ports.

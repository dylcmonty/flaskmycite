# Documentation Policy

This repository uses a canonical-docs model to avoid drift across portal instances.

## Canonical documentation location

- Canonical docs live under `docs/`.
- Root files may link to canonical docs, but should not duplicate long-form canonical content.

## Canonical docs (current)

- [`../README.md`](../README.md)
- [`mss_notes.md`](mss_notes.md)
- [`request_log_and_contracts.md`](request_log_and_contracts.md)
- [`DEVELOPMENT_PLAN.md`](DEVELOPMENT_PLAN.md)
- [`DOCUMENTATION_POLICY.md`](DOCUMENTATION_POLICY.md)
- [`DATA_TOOL.md`](DATA_TOOL.md)

## Example portal docs

- `mycite-ne-example/` and `mycite-le-example/` may contain lightweight local docs.
- Example docs should point back to canonical root docs instead of copying large design/spec text.
- Pointer docs are allowed under example-local `docs/` when they are short and link-oriented.

## Non-example portal docs

- Non-example portal folders (`mycite-ne_*`, `mycite-le_*`, excluding `*-example`) should not carry standalone design/spec docs.
- Minimum allowed:
  - top-level `README.md` (short portal summary + run notes + links to canonical docs)
- Operational docs required for runtime/security handling may remain, for example:
  - `private/request_log/README.md`
  - `vault/README.md`
- Tool-specific UI behavior should be implemented in `portal/tools/<tool_id>/` and surfaced through config-driven `enabled_tools`.
- Core UI templates/app wiring must not hardcode tool-specific tabs or sidebar entries.

## Archive docs

- `archive/*.md` files are historical reference material.
- Archive files are not canonical and should not be treated as active implementation spec unless promoted into `docs/`.

## Contributor checklist

- Add or update canonical guidance under `docs/` first.
- In portal subdirectories, prefer links to `/docs/*` over duplicated content.
- Keep non-example portal docs minimal and operational.

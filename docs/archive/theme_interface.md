# MyCite Theme Interface Standard (v0)

This standard defines how portal shells and embedded organization widgets apply user-selected themes.

## Theme Catalog

Supported theme IDs:
- `paper`
- `ocean`
- `forest`
- `midnight`

Default: `paper`

## Portal Theme Contract

The home page is the control surface for portal theme selection.

Home pages expose a selector with:
- `data-theme-selector`
- `data-theme-scope="portal"`

Alias pages may also include the same selector, but must use the same scope:
- `data-theme-selector`
- `data-theme-scope="portal"`

Alias pages expose the iframe with:
- `data-themed-iframe="1"`

`portal.js` must:
1. Read theme from URL `?theme=<id>` if present.
2. Otherwise read portal-wide local storage key `mycite.theme.portal.default`.
3. Fallback to `paper`.
4. Apply body class `theme-<id>`.
5. Ensure each themed iframe URL includes `?theme=<id>`.
6. Persist the selected theme to `mycite.theme.portal.default`.

## Embed Widget Contract

Organization widgets (`/portal/embed/poc`, `/portal/embed/tenant`) read `?theme=<id>` client-side.

Embed templates must:
- Accept the same four theme IDs.
- Sanitize invalid IDs to `paper`.
- Apply body class `theme-<id>`.

## CSS Contract

Portal styles define variable overrides on:
- `body.theme-paper`
- `body.theme-ocean`
- `body.theme-forest`
- `body.theme-midnight`

Widgets define equivalent theme classes in embed template styles to ensure visual parity inside iframes.

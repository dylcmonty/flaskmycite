# vault/

This directory documents how MyCite accesses secret material without embedding secrets in JSON.

## Non-negotiable policy
- Never commit private keys, symmetric keys, tokens, or credentials into this repository.
- Public keys may be published in `public/<msn_id>.json`.
- Config/contract JSON files must reference secrets using `key_ref` fields.

## KeePass (.kdbx) is the default vault
MyCite assumes secrets live in a portable, encrypted KeePass vault.

### What belongs in KeePass
Recommended entry fields:
- `private_key_pem`  (PKCS#8 / PEM)
- `hmac_key_b64`     (base64-encoded symmetric key for contract/magnet-link)
- `notes`            (non-sensitive notes only)

### Suggested entry naming
- Node signing key:
  - Title: `msn:<msn_id>:signing`
  - Field: `private_key_pem`
- Contract/magnet-link key:
  - Title: `contract:<contract_id>`
  - Field: `hmac_key_b64`

### `key_ref` convention
A `key_ref` identifies a vault entry and field; it does not contain secret material:

```json
{
  "key_ref": {
    "provider": "keepass",
    "vault_ref": "mycite.kdbx",
    "entry": "msn:3-2-...:signing",
    "field": "private_key_pem"
  }
}
```

Notes:
- `vault_ref` is an identifier. The runtime decides where the `.kdbx` lives.
- The portal UI must never read secrets; only backend code resolves `key_ref`.

## Key formats
Recommended:
- Private key: PKCS#8 PEM
- Public key: PEM

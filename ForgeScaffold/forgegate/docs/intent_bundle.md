# IntentBundle Format (v0.1)

An IntentBundle packages governance artifacts so teams can adopt ForgeGate quickly.

## Required structure
```
IntentBundle/
  catalogs/
    action_catalog.json
    signal_catalog.json
  intent/
    intent_spec.json
  governance/
    redaction_rules.yaml (optional)
  tests/
    scenarios/*.json
  meta.yaml
```

## Validation
```
forgegate validate-bundle ./IntentBundle
```

Validation ensures:
- required files exist
- catalogs and intent_spec match schemas
- scenarios include proposed_action, signals, expected.decision

Strict validation (recommended for CI/promotion):
```
forgegate validate-bundle ./IntentBundle --strict
forgegate lint-intent ./IntentBundle --strict
```

Strict mode also fails on policy warnings (for example, unknown top-level keys or empty policy specs).

## Signing & verification (optional)
Signing is offline and deterministic. Install the crypto extra first:
```
pip install -e '.[crypto]'
```

Sign a bundle:
```
forgegate sign-bundle ./IntentBundle --key ./keys/ed25519_private.pem
```

Verify a bundle:
```
forgegate verify-bundle ./IntentBundle --pubkey ./keys/ed25519_public.pem
```

Enforce signatures during validation:
```
forgegate validate-bundle ./IntentBundle --require-signature --pubkey ./keys/ed25519_public.pem
```

Signing excludes `signatures/` and transient files; the manifest is canonical JSON with sorted file paths.

## Example bundle
See `intent_bundle_example/` for a working bundle layout.

# Integrity & Signing (Phase 4)

## Bundle signing
```
forgegate sign-bundle ./IntentBundle --key ./keys/ed25519_private.pem
forgegate verify-bundle ./IntentBundle --pubkey ./keys/ed25519_public.pem
```

Signing produces:
- `IntentBundle/signatures/bundle.sig.json`
- `IntentBundle/signatures/bundle.manifest.json`
  
Keys are PEM:
- private: `ed25519_private.pem`
- public: `ed25519_public.pem`

## Ledger signing + checkpoints
```
forgegate sign-ledger ./ledger.jsonl --key ./keys/ed25519_private.pem --checkpoints ./checkpoints --every-n 100
forgegate verify-ledger ./ledger.jsonl --pubkey ./keys/ed25519_public.pem --checkpoints ./checkpoints
```

Checkpoints are tamper-evident and record the ledger head hash.

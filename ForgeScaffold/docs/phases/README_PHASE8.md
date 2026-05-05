# Phase 8: Multi-Signature Evidence + Signer Scopes/Expiry + Evidence Query

## What changed
- Evidence signing now supports multiple signatures in a single receipt.
- Trusted signer registry supports scopes (projects/pipelines) and expires_at.
- Evidence verification enforces signer trust, scope, and expiration.
- Evidence index query link provides structured audit queries.

## Pipelines
Strict (multi-sig):
```sh
python3 -m dawn.runtime.main --project <proj> --pipeline dawn/pipelines/forgescaffold_apply_v6_multisig.yaml --profile forgescaffold_apply_lowrisk
```

Runnable-only demo:
```sh
python3 -m dawn.runtime.main --project <proj> --pipeline dawn/pipelines/forgescaffold_apply_v6_multisig_runnable.yaml --profile forgescaffold_apply_lowrisk
```

## Trusted signer scopes
Edit the registry at `dawn/policy/trusted_signers.yaml`:
```yaml
trusted_signers:
  - fingerprint: "<fingerprint>"
    label: "ci-signer"
    scopes:
      projects: ["forgescaffold_phase8_ci"]
      pipelines: ["forgescaffold_apply_v6_multisig_runnable"]
    expires_at: "2030-01-01T00:00:00Z"
    revoked: false
```

## Verify evidence examples
PASS example (abridged):
```json
{
  "status": "PASS",
  "manifest_hash_ok": true,
  "receipt_ok": true,
  "required_signatures": 2,
  "valid_signatures": 2,
  "signers": [
    {"fingerprint": "<fp1>", "trusted": true, "scope_ok": true, "expired": false, "sig_ok": true},
    {"fingerprint": "<fp2>", "trusted": true, "scope_ok": true, "expired": false, "sig_ok": true}
  ]
}
```

FAIL example (abridged):
```json
{
  "status": "FAIL",
  "errors": ["SIGNER_SCOPE_VIOLATION"],
  "signers": [
    {"fingerprint": "<fp1>", "trusted": true, "scope_ok": false, "expired": false, "sig_ok": true}
  ]
}
```

## Evidence index query
Run the query link via any pipeline that includes `forgescaffold.query_evidence_index`, or by invoking the link directly if your DAWN setup supports single-link runs.

Configure filters in the link config (pipeline args or env):
- patchset_id
- approver
- risk_level
- since / until (RFC3339)
- limit

Example output:
```json
{
  "count": 1,
  "filters": {"patchset_id": "<id>", "limit": 5},
  "results": [
    {"patchset_id": "<id>", "risk_level": "medium", "status": "PASS"}
  ]
}
```

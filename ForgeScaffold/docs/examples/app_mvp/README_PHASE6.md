# ForgeScaffold Phase 6 (Trusted Signers + Evidence Verification)

This phase adds trusted signer enforcement, evidence verification, and review packet binding. The excerpts below show the PASS and FAIL states operators should expect.

## PASS example (non-tampered)
```json
{
  "errors": [],
  "manifest": {
    "hash_match": true,
    "signature_valid": true
  },
  "receipt": {
    "manifest_match": true
  },
  "signer": {
    "fingerprint": "80eeb72181cb6b000acda52069c2aa491b39fa713abf37aa5b3d7db54fb81193",
    "trusted": true
  },
  "status": "PASS"
}
```

PASS asserts:
- Signature is valid.
- Signer fingerprint is trusted by policy.
- Manifest hash matches both the receipt and the signature.
- Approval receipt matches patchset_id and bundle_content_sha256.

## FAIL example (tamper case)
```json
{
  "errors": [
    "SIGNATURE_INVALID",
    "MANIFEST_HASH_MISMATCH",
    "RECEIPT_MANIFEST_MISMATCH"
  ],
  "manifest": {
    "hash_match": false,
    "signature_valid": false
  },
  "receipt": {
    "manifest_match": false
  },
  "signer": {
    "fingerprint": "80eeb72181cb6b000acda52069c2aa491b39fa713abf37aa5b3d7db54fb81193",
    "trusted": true
  },
  "status": "FAIL"
}
```

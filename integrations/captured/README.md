# Captured Subsystem Outputs

## 1. Current Fixture Status

Representative hand-authored fixtures exist in `integrations/fixtures/`.

Current status:
- `representative_hand_authored` fixtures exist for CONCORD, ForgeGate, Warden, and Azul.
- Live smoke tests exist in `integrations/tests/test_runtime_fixtures.py`.
- Live smoke tests are skipped by default.

No real captured subsystem output files are currently included in this directory.

## 2. Capture Plan

### CONCORD

- Command/code path: run the CONCORD admission path for allow and deny scenarios.
- Expected output files:
  - `integrations/captured/concord_admission_allow_captured.json`
  - `integrations/captured/concord_admission_deny_captured.json`
- Required fields: `agent_id`, `admitted`, `reason`, `risk_level`, `tenant_id`, `customer_boundary`, `data_residency`, `policy_id`, `policy_hash`.
- Sensitivity notes: should not include raw credentials or customer secrets.
- Redaction requirements: no prompt redaction expected unless content-bearing fields are added.
- Reviewer: Control Mapping Reviewer and Ledger Administrator.

### ForgeGate

- Command/code path: run ForgeGate policy evaluation and decision record paths.
- Expected output files:
  - `integrations/captured/forgegate_policy_review_captured.json`
  - `integrations/captured/forgegate_decision_allow_captured.json`
- Required fields: `actor_id`, `decision_type`, `reason`, `risk_level`, `tenant_id`, `customer_boundary`, `data_residency`, `policy_id`, `policy_hash`, `action_type`.
- Sensitivity notes: policy context may include operational details; review before committing.
- Redaction requirements: no raw secrets in evidence refs or gap descriptions.
- Reviewer: Ledger Administrator and Compliance Analyst.

### Warden

- Command/code path: run Warden LLM gateway path with a deliberately sensitive prompt.
- Expected output file:
  - `integrations/captured/warden_llm_call_sensitive_captured.json`
- Required fields: `actor_id`, `decision_type`, `reason`, `risk_level`, `tenant_id`, `customer_boundary`, `data_residency`, `policy_id`, `policy_hash`, `prompt`, `response`, `data_sensitivity`, `prompt_class`, `response_class`, `model_provider`.
- Sensitivity notes: captured raw prompts may include personal or customer data. Do not commit real sensitive data unless scrubbed and approved.
- Redaction requirements: sensitive prompt/response must be redacted before storage in `ledger.jsonl`.
- Reviewer: Key Custodian, Legal Hold Officer if applicable, and Compliance Analyst.

### Azul

- Command/code path: run Azul safety verdict summary path.
- Expected output file:
  - `integrations/captured/azul_verdict_summary_captured.json`
- Required fields: `actor_id`, `verdict`, `reason`, `tenant_id`, `customer_boundary`, `data_residency`, `policy_id`, `policy_hash`, `safety_score`.
- Sensitivity notes: flagged categories should not expose raw unsafe content unless separately approved.
- Redaction requirements: no raw unsafe text in captured fixture unless scrubbed.
- Reviewer: Compliance Analyst and Control Mapping Reviewer.

## 3. Target Captured Files

- `integrations/captured/concord_admission_allow_captured.json`
- `integrations/captured/concord_admission_deny_captured.json`
- `integrations/captured/forgegate_policy_review_captured.json`
- `integrations/captured/forgegate_decision_allow_captured.json`
- `integrations/captured/warden_llm_call_sensitive_captured.json`
- `integrations/captured/azul_verdict_summary_captured.json`

## 4. Validation Plan

Captured output must pass:
- `normalize_*_output`
- Adapter emission
- `validate_event`
- Chain validation
- Sensitive Warden redaction before storage
- Evidence package build

Captured files must include `fixture_origin: captured_real_output`.

Do not fabricate captured output. If real subsystem output is unavailable, leave capture pending.

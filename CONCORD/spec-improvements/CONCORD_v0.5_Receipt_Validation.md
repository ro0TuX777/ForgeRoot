# CONCORD v0.5 — Receipt Validation Specification

**Status:** Normative Specification | **Version:** v0.5.1 | **Date:** April 2026  
**Extends:** CONCORD v0.3 Core Specification §3.3 (Receipt entity), v0.5 Admission Pipeline §11 (ReceiptMinting)  
**Related:** CONCORD v0.5.1 JSON Schema Adoption  

---

## 1. Purpose

CONCORD's Receipt entity captures the outcome of an executed Intent. It includes `result_summary` — structured data describing what the action produced. However, v0.3 does not specify validation of `result_summary` against the ActionContract's `output_schema`.

This creates a governance gap: an executor can return any shape of data, and the agent receives unvalidated output that may not match the declared schema. The agent cannot reliably parse the result for decision-making.

This specification makes Receipt validation a **mandatory stage** in the admission pipeline, and defines the error handling, logging, and recovery paths when validation fails.

---

## 2. Receipt Validation Requirements

### 2.1 When Validation Occurs

Receipt validation occurs at **Admission Pipeline Stage ⑪ — ReceiptMinting**, after:
- Execution has completed (stage ⑨)
- Output normalization has occurred (stage ⑩)
- The executor has returned `result_summary`

The validation is part of the **mandatory ReceiptMinting stage** (see Admission Pipeline §3.5).

### 2.2 Validation Algorithm

```
ReceiptMinting (Stage 11):
  1. Retrieve the executed Intent from datastore
  2. Retrieve the executor's ExecutionResult, including result_summary
  3. Retrieve the ActionContract from registry
  4. IF ActionContract.output_schema == null OR ActionContract.output_schema == {}:
       → Skip validation (no schema declared, vacuous pass)
       → Create Receipt with validation_skipped: true
  5. ELSE:
       → Validate result_summary against output_schema using JSON Schema validator
  6. IF validation passes:
       → Create Receipt with validation_passed: true
       → Deduct cost from BudgetLedger
       → Return Receipt to agent
  7. IF validation fails:
       → Create Receipt with validation_passed: false, validation_errors: [...]
       → Deduct cost from BudgetLedger (action still consumed resources)
       → Store Receipt and return OUTPUT_NORMALIZATION_FAILED error to agent
```

### 2.3 Cost Accounting with Validation Failures

**Important:** When Receipt validation fails, cost IS still deducted from the budget.

**Rationale:** The backend executed the action and consumed resources (compute, API calls, time). It is not the backend's fault that the output didn't match the declared schema — this is an integration contract violation, not a backend failure. The budget must reflect actual consumption.

**Exception:** If the executor signals `zero_cost: true` in the ExecutionResult (indicating no work was performed before failure), cost MUST NOT be deducted.

---

## 3. Receipt Entity Extensions (v0.5.1)

The Receipt entity gains new fields to track validation state:

```json
{
  "receipt_id": "rcp_xyz",
  "session_id": "sess_abc",
  "intent_id": "int_def",
  "action_name": "scan.pdf_analyze",
  
  "status": "completed",
  "result_summary": {
    "pages_analyzed": 42,
    "text_content": "...",
    "confidence_score": 0.95
  },
  
  "validation_passed": true,
  "validation_skipped": false,
  "validation_errors": [],
  
  "cost_deducted": 125,
  "created_at": "2026-04-08T14:32:00Z"
}
```

**New fields:**
- `validation_passed` (bool) — did result_summary conform to output_schema?
- `validation_skipped` (bool) — was validation skipped (no schema declared)?
- `validation_errors` (array) — if validation failed, detailed errors per field

### 3.1 Validation Error Detail

When `validation_passed: false`, `validation_errors` contains:

```json
{
  "validation_errors": [
    {
      "path": "confidence_score",
      "error": "Type mismatch",
      "expected_type": "number",
      "received_type": "string",
      "received_value": "0.95"
    },
    {
      "path": "pages_analyzed",
      "error": "Missing required field",
      "reason": "Field is required but not present in result_summary"
    },
    {
      "path": "extra_field",
      "error": "Additional property not allowed",
      "reason": "Schema does not allow additionalProperties"
    }
  ]
}
```

---

## 4. Error Handling & Agent Communication

### 4.1 OUTPUT_NORMALIZATION_FAILED Error

When Receipt validation fails, the agent receives:

```json
{
  "code": "OUTPUT_NORMALIZATION_FAILED",
  "severity": "elevated",
  "agent_should": "report",
  "requires_context_refresh": false,
  "detail": {
    "intent_id": "int_def",
    "receipt_id": "rcp_xyz",
    "action_name": "scan.pdf_analyze",
    "message": "Action executed but output did not conform to declared schema",
    "validation_summary": {
      "validation_passed": false,
      "field_errors": 2,
      "validation_errors": [
        {
          "path": "confidence_score",
          "error": "Type mismatch: expected number, got string '0.95'"
        },
        {
          "path": "pages_analyzed",
          "error": "Missing required field"
        }
      ]
    },
    "raw_result_summary": {
      "pages_analyzed_str": "42",
      "text_content": "...",
      "confidence_score": "0.95"
    },
    "troubleshooting": {
      "action": "Contact the integration team",
      "reason": "The normalizer did not produce output matching the declared output_schema. This is an integration contract violation, not an agent error.",
      "check_integration_logs": "See backend logs for executor output and normalizer trace"
    }
  }
}
```

**Agent's `agent_should: report`** indicates:
- The action executed
- The integration is broken (normalizer contract violation)
- The agent did nothing wrong and should escalate for human review

### 4.2 Audit Logging

Every Receipt validation event MUST be logged with:

```json
{
  "event": "receipt_validation",
  "timestamp": "2026-04-08T14:32:15Z",
  "action_name": "scan.pdf_analyze",
  "session_id": "sess_abc",
  "receipt_id": "rcp_xyz",
  "validation_passed": false,
  "validation_error_count": 2,
  "validation_duration_ms": 5,
  "cost_deducted": 125,
  "notes": "Type mismatch in confidence_score, missing pages_analyzed"
}
```

**Retention:** Validation events SHOULD be retained separately from Receipt records for analytics and integration health monitoring.

---

## 5. Integration Responsibilities

### 5.1 Building Valid Normalizers

The integration agent is responsible for ensuring normalizers produce output that conforms to `output_schema`.

**Normalizer testing requirements:**
1. Test normalizer against real backend output (happy path)
2. Test normalizer against edge cases (missing fields, null values, extra fields)
3. Verify that normalized output passes JSON Schema validation
4. If validation fails, adjust normalizer logic or relax schema constraints
5. **Before deployment:** run 100% coverage test of normalizer + validator

### 5.2 Exception Handling in Executors

If the backend returns output that the normalizer cannot process:

```python
# WRONG: Let exception propagate
def execute_scan(params):
    result = backend.scan(params['path'])
    return normalize_scan_result(result)  # Can throw

# RIGHT: Catch and return structured error
def execute_scan(params):
    try:
        result = backend.scan(params['path'])
        normalized = normalize_scan_result(result)
        return ExecutionResult(
            success=True,
            result_summary=normalized
        )
    except Exception as e:
        return ExecutionResult(
            success=False,
            error_code="EXECUTION_FAILED",
            error_detail=str(e)
        )
```

Errors during execution SHOULD NOT be "fixed" by the executor. They should be captured and returned as execution failures. The Receipt validation stage will then show whether the error output (if any) conforms to schema.

### 5.3 Schema Constraints Must Be Achievable

When designing `output_schema`, ensure that ALL normalizers can produce output matching it. Examples:

**WRONG:** Declare `required: ["match_count", "error_detail"]` when errors prevent providing `match_count`
```json
{
  "output_schema": {
    "type": "object",
    "properties": {
      "match_count": { "type": "integer" },
      "error_detail": { "type": "string" }
    },
    "required": ["match_count", "error_detail"]  // Impossible for error case
  }
}
```

**RIGHT:** Make error fields conditional or nullable
```json
{
  "output_schema": {
    "type": "object",
    "properties": {
      "match_count": { "type": ["integer", "null"] },
      "error_detail": { "type": ["string", "null"] },
      "success": { "type": "boolean" }
    },
    "required": ["success"]  // Only always-present field required
  }
}
```

---

## 6. Validation Semantics

### 6.1 Strict Schema Enforcement

Receipt validation MUST NOT:
- Perform type coercion (string "42" does NOT become integer 42)
- Drop extra properties silently (treat extra properties as validation failure if schema forbids them)
- Ignore required field absence (missing required fields are always failures)
- Attempt to "fix" the output (pass/fail only, no mutation)

### 6.2 Null Handling

If `output_schema` declares `type: "null"`, the action returns no data:

```json
{
  "output_schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "null"
  }
}
```

The executor MUST return either:
1. `result_summary: null` (passes validation)
2. `result_summary: {} ` (fails validation — extra properties not allowed)

### 6.3 Empty Object Handling

If `output_schema` declares only optional properties:

```json
{
  "output_schema": {
    "type": "object",
    "properties": {
      "optional_field": { "type": "string" }
    },
    "required": [],
    "additionalProperties": false
  }
}
```

The executor MAY return:
1. `result_summary: {}` (passes — empty object is valid)
2. `result_summary: { "optional_field": "value" }` (passes — optional field included)
3. `result_summary: { "other_field": "value" }` (fails — extra property)

---

## 7. Monitoring & Validation Health

### 7.1 Validation Metrics

Implementations SHOULD collect:

```
Receipt Validation Metrics by Action:
  - Total Receipts: count
  - Validation Passed: count
  - Validation Failed: count
  - Validation Skipped: count
  - Validation Pass Rate: %
  
Alerts to configure:
  - If validation_pass_rate < 99% for any action: SEV=HIGH
  - If any action has validation_failed count > 5 in 1 hour: SEV=CRITICAL
  - If validation takes > 100ms (validator is slow): SEV=MEDIUM
```

### 7.2 Debugging Validation Failures

When validation fails, include:

1. **Exact normalizer output** (what was produced)
2. **Expected schema** (what was required)
3. **Validator error messages** (field-level detail)
4. **Backend logs** (what the executor received from backend)
5. **Normalizer code** (line-by-line trace if available)

This helps integration teams quickly identify whether the problem is:
- Normalizer not transforming correctly
- Backend returning unexpected format
- Schema too strict/unrealistic

---

## 8. Conformance Requirements

All CONCORD v0.5.1 compliant implementations MUST:

1. Validate `result_summary` against `output_schema` at ReceiptMinting
2. Use JSON Schema Draft 2020-12 validator (see JSON Schema Adoption spec)
3. Return `OUTPUT_NORMALIZATION_FAILED` error when validation fails
4. Store validation results in Receipt with field-level detail
5. Deduct cost even on validation failure (unless `zero_cost: true`)
6. Log all validation events for audit trail
7. NOT mutate output to make it conform to schema
8. NOT attempt type coercion

---

## Appendix: Reference Implementation

### Python Receipt Validator

```python
import jsonschema
from jsonschema import Draft202012Validator, ValidationError

def validate_receipt(result_summary: dict, output_schema: dict) -> dict:
    """
    Validate result_summary against output_schema.
    
    Returns: {
        "validation_passed": bool,
        "validation_skipped": bool,
        "validation_errors": [...]
    }
    """
    
    # Handle null schema
    if output_schema is None or output_schema == {}:
        return {
            "validation_passed": True,
            "validation_skipped": True,
            "validation_errors": []
        }
    
    # Handle null type schema
    if output_schema.get("type") == "null":
        if result_summary is not None:
            return {
                "validation_passed": False,
                "validation_skipped": False,
                "validation_errors": [{
                    "path": "/",
                    "error": "Type mismatch",
                    "expected": "null",
                    "received_type": type(result_summary).__name__,
                    "received_value": str(result_summary)[:100]
                }]
            }
        return {
            "validation_passed": True,
            "validation_skipped": False,
            "validation_errors": []
        }
    
    # Validate with JSON Schema
    try:
        validator = Draft202012Validator(output_schema)
        errors = list(validator.iter_errors(result_summary))
        
        if errors:
            validation_errors = []
            for error in errors:
                path = "/" + "/".join(str(p) for p in error.absolute_path) if error.absolute_path else "/"
                validation_errors.append({
                    "path": path,
                    "error": error.validator,
                    "message": error.message,
                    "schema_part": str(error.schema)[:200]
                })
            
            return {
                "validation_passed": False,
                "validation_skipped": False,
                "validation_errors": validation_errors
            }
        
        return {
            "validation_passed": True,
            "validation_skipped": False,
            "validation_errors": []
        }
    
    except Exception as e:
        # Validator itself failed (schema is malformed)
        return {
            "validation_passed": False,
            "validation_skipped": False,
            "validation_errors": [{
                "path": "/",
                "error": "ValidatorError",
                "message": str(e)
            }]
        }


def mint_receipt(intent, execution_result, action_contract, ledger):
    """
    Mint a Receipt with validation.
    """
    # Validate output
    validation_result = validate_receipt(
        execution_result.result_summary,
        action_contract.output_schema
    )
    
    # Create Receipt
    receipt = Receipt(
        receipt_id=generate_id(),
        session_id=intent.session_id,
        intent_id=intent.intent_id,
        action_name=intent.action_name,
        status="completed",
        result_summary=execution_result.result_summary,
        validation_passed=validation_result["validation_passed"],
        validation_skipped=validation_result["validation_skipped"],
        validation_errors=validation_result["validation_errors"],
        cost_deducted=0
    )
    
    # Deduct cost (regardless of validation)
    if not execution_result.zero_cost:
        ledger.deduct(
            session_id=intent.session_id,
            category=action_contract.cost_category,
            amount=action_contract.cost
        )
        receipt.cost_deducted = action_contract.cost
    
    # Store Receipt
    receipts_db.store(receipt)
    
    return receipt
```


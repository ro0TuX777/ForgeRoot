# CONCORD v0.5 — JSON Schema Adoption

**Status:** Normative Specification | **Version:** v0.5.1 | **Date:** April 2026  
**Extends:** CONCORD v0.3 Core Specification §3.2, v0.5 Admission Pipeline Specification §6  
**Replaces:** Ambiguous schema format guidance in v0.3  

---

## 1. Purpose

CONCORD's ActionContract entity declares `input_schema` and `output_schema` to communicate the structure of data the agent must provide and the structure of data the agent will receive. However, v0.3 does not specify the schema format itself. Integration agents invented custom formats, leading to inconsistent validation implementations and confusion.

This specification adopts **JSON Schema (Draft 2020-12)** as the normative schema format for all ActionContracts. This removes ambiguity and allows integration agents to use standard JSON Schema validators across multiple languages.

---

## 2. JSON Schema Baseline

### 2.1 Schema URI

All schemas MUST include:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  ...
}
```

### 2.2 Supported JSON Schema Features

Implementations MUST support:

| Feature | Support | Notes |
|---|---|---|
| type | REQUIRED | object, array, string, integer, number, boolean, null |
| properties | REQUIRED | Object schema property definitions |
| required | REQUIRED | Array of required property names |
| items | REQUIRED | For array type constraints |
| enum | REQUIRED | Fixed set of allowed values |
| const | REQUIRED | Single allowed value |
| minimum / maximum | REQUIRED | Numeric bounds |
| minLength / maxLength | REQUIRED | String length bounds |
| pattern | REQUIRED | Regex string patterns |
| additionalProperties | REQUIRED | Allow/deny extra properties |
| default | OPTIONAL | Default values for fields |
| description | OPTIONAL | Human-readable field descriptions |
| examples | OPTIONAL | Sample values for documentation |
| $ref | OPTIONAL | Cross-references and definitions |
| allOf / oneOf / anyOf | OPTIONAL | Composition (schemas MAY use, validators MUST support) |
| format | OPTIONAL | Built-in formats (see 2.3) |

**Not supported:**
- `$dynamicRef`, `$dynamicAnchor` (too complex for this use case)
- Unevaluated properties / unevaluated items (implementations MAY skip these)
- Custom keywords

### 2.3 Format Specifications

When `"format"` is used, these formats are normatively defined:

| Format | Type | Definition | Validation |
|---|---|---|---|
| `date` | string | RFC 3339 date (`YYYY-MM-DD`) | MUST validate structure |
| `time` | string | RFC 3339 time (`HH:MM:SSZ`) | MUST validate structure |
| `date-time` | string | RFC 3339 date-time with timezone | MUST validate structure, timezone aware |
| `uri` | string | RFC 3986 URI | MUST validate structure |
| `uuid` | string | RFC 4122 UUID | MUST validate format |
| `email` | string | RFC 5322 email | SHOULD validate with basic regex |

**Note on date-time:** CONCORD's datetime formats MUST be timezone-aware. Infrastructure MUST reject naive datetimes in formats that expect timezone info.

### 2.4 Reference Validators

Implementations SHOULD use an established JSON Schema validator library:

- **Python:** `jsonschema` (PyPI) or `python-jsonschema`
- **JavaScript/Node:** `ajv` (npm) or `jsonschema`
- **Go:** `github.com/xeipuuv/gojsonschema`
- **Java:** `json-schema-validator` or `everit-org/json-schema`

All must validate against Draft 2020-12 or compatible version.

---

## 3. ActionContract Schema Declarations

### 3.1 Input Schema

Every ActionContract MUST declare `input_schema`:

**If the action accepts parameters:**
```json
{
  "action_name": "scan.pdf_analyze",
  "input_schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
      "pdf_path": {
        "type": "string",
        "description": "Absolute path to PDF file",
        "format": "uri"
      },
      "max_pages": {
        "type": "integer",
        "description": "Maximum pages to analyze (0 = all)",
        "minimum": 0,
        "default": 0
      },
      "extract_images": {
        "type": "boolean",
        "description": "Whether to extract embedded images",
        "default": false
      }
    },
    "required": ["pdf_path"],
    "additionalProperties": false
  }
}
```

**If the action accepts NO parameters:**
```json
{
  "action_name": "system.health_check",
  "input_schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": false
  }
}
```

**Why even empty actions need a schema:** It signals to agents that parameters are intentionally not accepted, rather than leaving it ambiguous whether parameters are optional or forbidden.

### 3.2 Output Schema

Every ActionContract MUST declare `output_schema`:

**If the action returns data:**
```json
{
  "action_name": "scan.pdf_analyze",
  "output_schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
      "pages_analyzed": {
        "type": "integer",
        "description": "Number of pages successfully analyzed"
      },
      "text_content": {
        "type": "string",
        "description": "Concatenated text from all analyzed pages"
      },
      "images_extracted": {
        "type": "integer",
        "description": "Number of images extracted (if requested)"
      },
      "confidence_score": {
        "type": "number",
        "minimum": 0,
        "maximum": 1,
        "description": "Confidence in text extraction (0-1)"
      },
      "extraction_warnings": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Any warnings encountered during analysis"
      }
    },
    "required": ["pages_analyzed", "text_content", "confidence_score"],
    "additionalProperties": false
  }
}
```

**If the action returns NO data (or only status):**
```json
{
  "action_name": "resource.cleanup",
  "output_schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "null"
  }
}
```

### 3.3 Schema Composition with $ref

For reusable field definitions, use `$defs`:

```json
{
  "action_name": "report.generate",
  "input_schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
      "format": {
        "type": "string",
        "enum": ["json", "csv", "pdf"]
      },
      "filters": {
        "$ref": "#/$defs/FilterObject"
      }
    },
    "required": ["format"],
    "$defs": {
      "FilterObject": {
        "type": "object",
        "properties": {
          "date_start": { "type": "string", "format": "date" },
          "date_end": { "type": "string", "format": "date" },
          "severity_min": { "type": "integer", "minimum": 0, "maximum": 5 }
        }
      }
    }
  }
}
```

---

## 4. Validation Semantics

### 4.1 Admission Pipeline Stage ⑥ — InputValidation

The InputValidation stage MUST:

1. Retrieve the resolved ActionContract
2. Extract the `input_schema` from the contract
3. Validate the intent's `parameters` against the schema
4. If validation succeeds → pass to next stage
5. If validation fails → return `INVALID_PARAMETERS` error (see §4.2)

**Validation rules:**
- Validate using a JSON Schema Draft 2020-12 compliant validator
- Treat missing required fields as validation failure
- Treat extra properties as validation failure (if `additionalProperties: false`)
- Treat type mismatches as validation failure
- Type coercion is NOT permitted (if schema expects integer and receives string "42", fail)

### 4.2 INVALID_PARAMETERS Error Response

When InputValidation fails, return:

```json
{
  "code": "INVALID_PARAMETERS",
  "severity": "moderate",
  "agent_should": "recheck",
  "requires_context_refresh": true,
  "detail": {
    "action_name": "scan.pdf_analyze",
    "missing_required_fields": ["pdf_path"],
    "type_errors": [
      {
        "field": "max_pages",
        "expected_type": "integer",
        "received_type": "string",
        "received_value": "300",
        "reason": "Type coercion not permitted"
      }
    ],
    "constraints_violated": [
      {
        "field": "max_pages",
        "constraint": "minimum",
        "expected_minimum": 0,
        "received_value": -1,
        "reason": "Value violates minimum constraint"
      }
    ],
    "extra_properties": ["unknown_field"],
    "validation_hints": [
      "See OperationContext for this action for the complete schema",
      "All required fields: pdf_path",
      "No additional properties are allowed"
    ]
  }
}
```

### 4.3 Receipt Validation (Stage ⑪ — ReceiptMinting)

The ReceiptMinting stage MUST:

1. Retrieve the completed execution's `result_summary` from the executor
2. Retrieve the action's `output_schema` from the ActionContract
3. Validate `result_summary` against the schema
4. On success → mint Receipt with `result_summary` as-is
5. On failure → mint Receipt with `validation_failed: true` and store validation errors

**If Receipt validation fails:**
- The Receipt is still created and stored (the action executed, the output just didn't conform)
- The Receipt status is `executed_output_mismatch`
- The Receipt includes`output_validation_errors` in its metadata
- The agent receives an error code `OUTPUT_NORMALIZATION_FAILED` (see Admission Pipeline §3.4)

**Key rule:** No action's unstructured output bypasses the schema contract. If an executor returns output that doesn't conform to `output_schema`, the governance contract is broken and must be reported.

---

## 5. Schema Versioning & Deprecation

### 5.1 Schema Stability

Once an `input_schema` or `output_schema` is published in a production ActionContract, **it should not change** in ways that break existing agents.

**Safe changes:**
- Adding new optional properties to an object schema
- Adding new `enum` values
- Relaxing constraints (e.g., increasing minLength, or increasing maximum)
- Adding `$defs` for internal composition

**Breaking changes:**
- Removing a required field
- Adding a new required field without default
- Changing a field's type
- Adding `additionalProperties: false` when it was previously true
- Tightening constraints (e.g., decreasing minLength, increasing minimum)

### 5.2 Schema Evolution

If an ActionContract's schema MUST change in a breaking way:

1. Create a new ActionContract with a versioned name (e.g., `scan.pdf_analyze.v2`) with the new schema
2. Mark the old ActionContract as `deprecated: true` (see Error Catalog for `ACTION_DEPRECATED` error)
3. Include a `migration_hint` in the ActionContract metadata telling agents which new action to use
4. Maintain the old action for a deprecation window (at least one full quarterly release)
5. Log agents using the deprecated action for audit trail

---

## 6. Integration Guide for Schema Usage

When building an ActionContract:

1. **Define input_schema first** — what parameters does this capability need?
2. **Define output_schema next** — what does the agent need to know about the result?
3. **Write a normalizer** — translate raw backend output to match output_schema (see Normalizer Spec)
4. **Test validation** — verify that valid inputs pass and invalid inputs fail correctly
5. **Document examples** — include `examples` in schema properties so agents understand the expected shape

---

## 7. Reference Implementation: Python Validator

```python
import jsonschema
from jsonschema import Draft202012Validator, ValidationError

def validate_input(parameters: dict, input_schema: dict) -> (bool, list[str]):
    """
    Validate parameters against input_schema.
    Returns: (is_valid, error_messages)
    """
    try:
        validator = Draft202012Validator(input_schema)
        errors = list(validator.iter_errors(parameters))
        
        if errors:
            error_messages = [f"{'/'.join(str(p) for p in e.path)}: {e.message}" 
                            for e in errors]
            return False, error_messages
        return True, []
    except Exception as e:
        return False, [f"Validator error: {str(e)}"]

def validate_output(result: dict, output_schema: dict) -> (bool, list[str]):
    """
    Validate result_summary against output_schema.
    Returns: (is_valid, error_messages)
    """
    # Handles null schema specially
    if output_schema.get("type") == "null":
        if result is None:
            return True, []
        return False, ["Expected null output, received data"]
    
    return validate_input(result, output_schema)
```

---

## 8. Conformance Requirements

All CONCORD v0.5.1 compliant implementations MUST:

1. Use JSON Schema Draft 2020-12 for all `input_schema` and `output_schema` fields
2. Include `"$schema": "https://json-schema.org/draft/2020-12/schema"` in every schema
3. Validate using a Draft 2020-12 compliant validator
4. Return `INVALID_PARAMETERS` errors with structured field-level detail
5. Validate Receipt outputs against `output_schema` at minting time
6. Treat mismatched outputs as a governance violation
7. Support schema composition with `$defs` and `$ref`
8. Not permit type coercion in validation

---

## Appendix: Examples

### Example 1: File Processing Action

```json
{
  "action_name": "file.convert_format",
  "input_schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
      "source_path": {
        "type": "string",
        "description": "Path to source file"
      },
      "target_format": {
        "type": "string",
        "enum": ["json", "csv", "xml", "yaml"],
        "description": "Target output format"
      },
      "encoding": {
        "type": "string",
        "default": "utf-8",
        "description": "Character encoding for output"
      }
    },
    "required": ["source_path", "target_format"],
    "additionalProperties": false
  },
  "output_schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
      "conversion_success": {
        "type": "boolean"
      },
      "output_path": {
        "type": "string",
        "description": "Path where converted file was written"
      },
      "bytes_written": {
        "type": "integer",
        "minimum": 0
      },
      "warnings": {
        "type": "array",
        "items": { "type": "string" }
      }
    },
    "required": ["conversion_success", "output_path"],
    "additionalProperties": false
  }
}
```

### Example 2: Query Action (No Parameters)

```json
{
  "action_name": "system.status_check",
  "input_schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": false
  },
  "output_schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
      "healthy": {
        "type": "boolean"
      },
      "uptime_ms": {
        "type": "integer",
        "minimum": 0
      },
      "services": {
        "type": "object",
        "properties": {
          "database": { "type": "boolean" },
          "cache": { "type": "boolean" },
          "queue": { "type": "boolean" }
        }
      }
    },
    "required": ["healthy"],
    "additionalProperties": false
  }
}
```


# CONCORD Integration — Normalizer Specification & Templates

**Status:** Normative Integration Guidance | **Version:** v0.5.1 | **Date:** April 2026  
**Extends:** Integration Lessons Camp 2 §2.5, CONCORD v0.5.1 JSON Schema Adoption, Receipt Validation  

---

## 1. Purpose

The normalizer is the critical component that transforms backend output into structured, schema-conformant data that agents can reliably consume. Integration Lessons identified output normalization as **"the highest-value work in the entire integration."**

This specification formalizes:
- What normalizers are and why they're essential
- Contract signature and error handling
- Testing strategy to ensure quality
- Reusable templates for common patterns
- Common pitfalls and how to avoid them

---

## 2. Normalizer Concept

### 2.1 Definition

A **normalizer** is a function that transforms backend output into structured data conforming to an ActionContract's `output_schema`.

```
Normalizer signature (pseudo-code):

Input:
  raw_output          (any)              — whatever the backend returned
  action_contract     (ActionContract)   — the action being executed
  
Output:
  NormalizationResult {
    normalized:       object             — structured output conforming to output_schema
    success:          bool               — did normalization succeed?
    warnings:         string[]           — issues encountered (non-fatal)
    error_detail:     string?            — if success=false, why?
  }
```

### 2.2 Why Normalizers Are Essential

The backend application was built for **humans**. Its outputs are shaped for human consumption:

- HTML pages with nested divs and CSS classes
- Formatted text logs with embedded status codes
- Nested dictionaries with inconsistent field names
- File paths, memory addresses, timestamps in non-standard formats
- Verbose error messages mixed with useful data

**Agents cannot work with this.** Agents need:
- Structured, consistent field names
- Predictable data types
- Extractable meaning (severity levels, counts, pass/fail status)
- No embedded prose that requires language understanding

**Normalizers bridge this gap.** They are the integration's way of saying: "The backend does X, the agent needs to know Y, here's how we transform X into Y."

### 2.3 Why Normalizers Are NOT Executors

The **executor** handles the integration between CONCORD and the backend:
- Parameter translation (CONCORD parameter names → backend parameter names)
- Exception classification (backend exceptions → CONCORD error codes)
- Basic output retrieval (get the raw result from the backend)

The **normalizer** handles the integration between the backend's output and the agent's expectations:
- Extract meaningful data from messy output
- Map to schema field names
- Aggregate or compute field values
- Format timestamps, paths, etc.

**Clear separation of concerns:**
```
Agent Intent
    ↓
Executor: translate parameters, call backend, catch exceptions
    ↓
Normalizer: transform output to schema-conformant structure
    ↓
Receipt (with validated result_summary)
    ↓
Agent
```

---

## 3. Normalizer Contract

### 3.1 Signature (Multiple Languages)

**Python:**
```python
from dataclasses import dataclass
from typing import Any, List, Optional, Dict

@dataclass
class NormalizationResult:
    normalized: Optional[Dict[str, Any]]
    success: bool
    warnings: List[str]
    error_detail: Optional[str] = None

def normalize_[action]_(raw_output: Any, action_contract: Dict[str, Any]) -> NormalizationResult:
    """
    Transform backend output to match output_schema.
    
    MUST NOT raise exceptions. Always return a NormalizationResult.
    """
    pass
```

**JavaScript/TypeScript:**
```typescript
interface NormalizationResult {
  normalized: any;
  success: boolean;
  warnings: string[];
  errorDetail?: string;
}

function normalize[Action](rawOutput: any, actionContract: any): NormalizationResult {
  // MUST NOT throw. Always return NormalizationResult.
}
```

**Python (Reference):**
```python
def normalize_pdf_analysis(raw_output, action_contract):
    """
    Transform PDF analysis output to schema.
    Output schema expects: { pages_analyzed, text_content, confidence_score, warnings }
    """
    result = NormalizationResult(
        normalized=None,
        success=True,
        warnings=[]
    )
    
    try:
        if raw_output is None:
            result.success = False
            result.error_detail = "Backend returned None"
            return result
        
        # Extract fields
        normalized = {}
        
        # pages_analyzed: required
        if "num_pages" in raw_output:
            normalized["pages_analyzed"] = int(raw_output["num_pages"])
        else:
            result.warnings.append("Backend did not return page count")
            normalized["pages_analyzed"] = 0
        
        # text_content: required
        if "extracted_text" in raw_output:
            normalized["text_content"] = str(raw_output["extracted_text"])
        else:
            result.success = False
            result.error_detail = "Backend did not return extracted text"
            return result
        
        # confidence_score: required, must be 0-1
        if "extraction_confidence" in raw_output:
            confidence = float(raw_output["extraction_confidence"])
            if not (0 <= confidence <= 1):
                result.warnings.append(f"Confidence {confidence} out of range, clamping")
                confidence = max(0, min(1, confidence))
            normalized["confidence_score"] = confidence
        else:
            result.warnings.append("No confidence score, defaulting to 0.5")
            normalized["confidence_score"] = 0.5
        
        # warnings: optional array
        if "processing_warnings" in raw_output:
            normalized["warnings"] = raw_output["processing_warnings"]
        else:
            normalized["warnings"] = []
        
        result.normalized = normalized
        return result
    
    except Exception as e:
        result.success = False
        result.error_detail = f"Normalizer exception: {str(e)}"
        return result
```

### 3.2 Rules

**MUST:**
1. Accept any `raw_output` (don't assume type/structure)
2. Always return a `NormalizationResult` (never raise exceptions)
3. Include required fields in normalized output (even if with defaults)
4. Document assumptions about backend output
5. Return `success: false` if the output is unusable
6. Include warnings for unexpected conditions

**MUST NOT:**
1. Return None or raise exceptions
2. Assume backend always returns the exact same structure
3. Fail silently (if something is wrong, include it in warnings)
4. Allocate resources or call external services
5. Modify `raw_output` (work with a copy if needed)
6. Perform I/O (read files, call APIs, etc.)

---

## 4. Common Normalization Patterns

### 4.1 Pattern: HTML/Rich Text to Structured Data

**Backend returns:** HTML report with nested divs and styling
**Agent needs:** Structured metrics/results

**Template:**
```python
def normalize_html_report(raw_output, action_contract):
    result = NormalizationResult(normalized={}, success=True, warnings=[])
    
    try:
        from html.parser import HTMLParser
        
        if isinstance(raw_output, str):
            html = raw_output
        else:
            html = str(raw_output)
        
        # Parse with a simple HTML extractor
        parser = SimpleHTMLExtractor()
        parser.feed(html)
        
        # Extract metrics
        normalized = {
            "total_items": len(parser.items),
            "passed_count": sum(1 for item in parser.items if item.get("status") == "pass"),
            "failed_count": sum(1 for item in parser.items if item.get("status") == "fail"),
            "items": parser.items
        }
        
        if normalized["total_items"] == 0:
            result.warnings.append("Report contained no items")
        
        result.normalized = normalized
        return result
    
    except Exception as e:
        result.success = False
        result.error_detail = str(e)
        return result
```

### 4.2 Pattern: Log Output to Parsed Events

**Backend returns:** Log file or log lines
**Agent needs:** Structured events with severity levels

**Template:**
```python
def normalize_log_output(raw_output, action_contract):
    result = NormalizationResult(normalized={}, success=True, warnings=[])
    
    try:
        if isinstance(raw_output, str):
            lines = raw_output.split("\n")
        else:
            lines = list(raw_output)
        
        events = []
        severity_counts = {"debug": 0, "info": 0, "warning": 0, "error": 0}
        
        for line in lines:
            if not line.strip():
                continue
            
            # Parse line (adapt regex to your backend)
            match = re.match(r"\[(\w+)\]\s+(.+)", line)
            if match:
                severity = match.group(1).lower()
                message = match.group(2)
                
                events.append({
                    "severity": severity,
                    "message": message,
                    "raw_line": line
                })
                
                if severity in severity_counts:
                    severity_counts[severity] += 1
            else:
                result.warnings.append(f"Could not parse log line: {line[:50]}")
        
        normalized = {
            "total_events": len(events),
            "severity_distribution": severity_counts,
            "events": events,
            "has_errors": severity_counts["error"] > 0
        }
        
        result.normalized = normalized
        return result
    
    except Exception as e:
        result.success = False
        result.error_detail = str(e)
        return result
```

### 4.3 Pattern: Nested Dict to Flat Schema

**Backend returns:** Deeply nested dictionary with inconsistent keys
**Agent needs:** Flat structure with consistent field names

**Template:**
```python
def normalize_nested_result(raw_output, action_contract):
    result = NormalizationResult(normalized={}, success=True, warnings=[])
    
    try:
        if not isinstance(raw_output, dict):
            result.success = False
            result.error_detail = f"Expected dict, got {type(raw_output).__name__}"
            return result
        
        # Map backend keys to schema keys
        key_mapping = {
            "backend_key": "schema_field",
            "nested.path.key": "flattened_field"
        }
        
        normalized = {}
        
        for backend_key, schema_key in key_mapping.items():
            value = _get_nested(raw_output, backend_key)
            if value is not None:
                normalized[schema_key] = value
            else:
                result.warnings.append(f"Missing backend field: {backend_key}")
                normalized[schema_key] = None
        
        result.normalized = normalized
        return result
    
    except Exception as e:
        result.success = False
        result.error_detail = str(e)
        return result

def _get_nested(d, path):
    """Get value from nested dict using dot notation."""
    for key in path.split("."):
        if isinstance(d, dict):
            d = d.get(key)
        else:
            return None
    return d
```

### 4.4 Pattern: File Path to File Content

**Backend returns:** Path to a file
**Agent needs:** File contents or metadata

**Template:**
```python
def normalize_file_result(raw_output, action_contract):
    result = NormalizationResult(normalized={}, success=True, warnings=[])
    
    try:
        file_path = None
        if isinstance(raw_output, str):
            file_path = raw_output
        elif isinstance(raw_output, dict) and "path" in raw_output:
            file_path = raw_output["path"]
        
        if not file_path:
            result.success = False
            result.error_detail = "Could not determine file path"
            return result
        
        # Read file within size limits
        MAX_SIZE = 1_000_000  # 1MB
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read(MAX_SIZE)
                if len(content) == MAX_SIZE:
                    result.warnings.append("File too large, truncated to 1MB")
        except Exception as e:
            result.success = False
            result.error_detail = f"Could not read file: {str(e)}"
            return result
        
        normalized = {
            "file_path": file_path,
            "file_size": len(content),
            "content": content,
            "truncated": len(content) == MAX_SIZE
        }
        
        result.normalized = normalized
        return result
    
    except Exception as e:
        result.success = False
        result.error_detail = str(e)
        return result
```

### 4.5 Pattern: Multiple Output Formats (Union Type)

**Backend returns:** Different structure depending on success/failure
**Agent needs:** Unified schema with status indicator

**Template:**
```python
def normalize_result_with_status(raw_output, action_contract):
    result = NormalizationResult(normalized={}, success=True, warnings=[])
    
    try:
        normalized = {
            "success": False,
            "data": None,
            "error": None
        }
        
        # Handle different return types
        if isinstance(raw_output, dict):
            # Case 1: Success response
            if raw_output.get("status") == "success":
                normalized["success"] = True
                normalized["data"] = raw_output.get("payload")
            
            # Case 2: Error response
            elif raw_output.get("status") == "error":
                normalized["success"] = False
                normalized["error"] = raw_output.get("error_message")
            
            # Case 3: Unknown format
            else:
                result.warnings.append(f"Unknown response format: {raw_output}")
                normalized["success"] = False
        
        elif isinstance(raw_output, list):
            # Treat list as successful array result
            normalized["success"] = True
            normalized["data"] = raw_output
        
        else:
            result.success = False
            result.error_detail = f"Unexpected type: {type(raw_output).__name__}"
            return result
        
        result.normalized = normalized
        return result
    
    except Exception as e:
        result.success = False
        result.error_detail = str(e)
        return result
```

---

## 5. Testing Normalizers

### 5.1 Test Harness Template

```python
import pytest
from action_contract import ActionContract
from normalizers import normalize_pdf_analysis

@pytest.fixture
def action_contract():
    return ActionContract(
        action_name="scan.pdf_analysis",
        output_schema={
            "type": "object",
            "properties": {
                "pages_analyzed": {"type": "integer"},
                "text_content": {"type": "string"},
                "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
                "warnings": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["pages_analyzed", "text_content", "confidence_score"]
        }
    )

class TestPDFNormalizer:
    
    def test_happy_path_complete_output(self, action_contract):
        """Test normalizer with complete, clean backend output."""
        raw_output = {
            "num_pages": 42,
            "extracted_text": "Lorem ipsum...",
            "extraction_confidence": 0.95,
            "processing_warnings": []
        }
        
        result = normalize_pdf_analysis(raw_output, action_contract)
        
        assert result.success
        assert result.normalized["pages_analyzed"] == 42
        assert result.normalized["confidence_score"] == 0.95
        assert len(result.warnings) == 0
    
    def test_missing_optional_fields(self, action_contract):
        """Test normalizer with missing optional fields."""
        raw_output = {
            "num_pages": 10,
            "extracted_text": "Content...",
            "extraction_confidence": 0.87
            # Missing processing_warnings
        }
        
        result = normalize_pdf_analysis(raw_output, action_contract)
        
        assert result.success
        assert result.normalized["warnings"] == []
        assert len(result.warnings) > 0  # Should warn about missing field
    
    def test_missing_required_fields(self, action_contract):
        """Test normalizer with missing required fields."""
        raw_output = {
            "num_pages": 5,
            # Missing extracted_text (required)
            "extraction_confidence": 0.9
        }
        
        result = normalize_pdf_analysis(raw_output, action_contract)
        
        assert not result.success
        assert result.error_detail is not None
    
    def test_type_mismatch_handling(self, action_contract):
        """Test normalizer handles type mismatches gracefully."""
        raw_output = {
            "num_pages": "42",  # string instead of int
            "extracted_text": "Content...",
            "extraction_confidence": 0.9
        }
        
        result = normalize_pdf_analysis(raw_output, action_contract)
        
        # Should convert or warn, not fail
        assert result.success or len(result.warnings) > 0
    
    def test_out_of_range_values(self, action_contract):
        """Test normalizer clamps out-of-range numeric values."""
        raw_output = {
            "num_pages": 5,
            "extracted_text": "Content...",
            "extraction_confidence": 1.5  # Out of range [0, 1]
        }
        
        result = normalize_pdf_analysis(raw_output, action_contract)
        
        assert result.success
        assert 0 <= result.normalized["confidence_score"] <= 1
        assert len(result.warnings) > 0  # Should warn about clamping
    
    def test_none_output(self, action_contract):
        """Test normalizer with None output."""
        result = normalize_pdf_analysis(None, action_contract)
        
        assert not result.success
        assert result.error_detail is not None
    
    def test_output_validates_against_schema(self, action_contract):
        """Test that normalized output validates against output_schema."""
        raw_output = {
            "num_pages": 8,
            "extracted_text": "Valid content",
            "extraction_confidence": 0.88,
            "processing_warnings": ["Warning 1"]
        }
        
        result = normalize_pdf_analysis(raw_output, action_contract)
        
        if result.success:
            # Validate normalized output against schema
            from jsonschema import validate
            validate(instance=result.normalized, schema=action_contract.output_schema)
```

### 5.2 Validation Integration

```python
import jsonschema

def validate_normalizer_output(normalized_output, output_schema):
    """
    Verify normalized output conforms to output_schema.
    Used after normalizer runs, before Receipt minting.
    """
    try:
        validator = jsonschema.Draft202012Validator(output_schema)
        validator.validate(normalized_output)
        return True, []
    except jsonschema.ValidationError as e:
        return False, [str(e)]
    except Exception as e:
        return False, [f"Validation error: {str(e)}"]
```

---

## 6. Common Pitfalls

### Pitfall 1: Silent Failures

**WRONG:**
```python
def normalize_result(raw_output, action_contract):
    try:
        # ... processing
        return NormalizationResult(normalized={...}, success=True, warnings=[])
    except:
        # Silent failure
        return NormalizationResult(normalized={}, success=True, warnings=[])
```

**RIGHT:**
```python
def normalize_result(raw_output, action_contract):
    try:
        # ... processing
        return NormalizationResult(normalized={...}, success=True, warnings=[])
    except Exception as e:
        return NormalizationResult(
            normalized=None,
            success=False,
            warnings=[],
            error_detail=f"Normalizer failed: {str(e)}"
        )
```

### Pitfall 2: Assuming Backend Structure

**WRONG:**
```python
def normalize_result(raw_output, action_contract):
    # Assume raw_output is always a dict with these exact keys
    return NormalizationResult(
        normalized={
            "count": raw_output["items"],
            "result": raw_output["data"]["payload"]["result"]
        },
        success=True,
        warnings=[]
    )
```

**RIGHT:**
```python
def normalize_result(raw_output, action_contract):
    if not isinstance(raw_output, dict):
        return NormalizationResult(success=False, error_detail=f"Expected dict")
    
    count = raw_output.get("items")
    if count is None:
        return NormalizationResult(success=False, error_detail="Missing 'items'")
    
    # Safely navigate nested structure
    payload = (raw_output.get("data") or {}).get("payload") or {}
    result = payload.get("result")
    
    return NormalizationResult(
        normalized={"count": count, "result": result},
        success=True,
        warnings=[] if result else ["Missing nested result"]
    )
```

### Pitfall 3: Type Coercion

**WRONG:**
```python
# Attempt to convert type
normalized["timeout_seconds"] = int(raw_output.get("timeout", "300"))
```

**RIGHT:**
```python
# Validate type matches schema
if isinstance(raw_output.get("timeout"), int):
    normalized["timeout_seconds"] = raw_output["timeout"]
else:
    result.warnings.append(f"timeout is {type(raw_output.get('timeout'))}, expected int")
    normalized["timeout_seconds"] = 300  # Default
```

### Pitfall 4: Normalizer Imports/IO

**WRONG:**
```python
def normalize_result(raw_output, action_contract):
    # Normalizer should not do I/O or call external services
    import requests
    response = requests.get("https://api.example.com/enrich", json=raw_output)
    # ...
```

**RIGHT:**
```python
def normalize_result(raw_output, action_contract):
    # Normalizer only transforms what it received
    # Enrichment should be a separate action if needed
    normalized = extract_and_structure(raw_output)
    return NormalizationResult(normalized=normalized, success=True)
```

---

## 7. Checklist for Integration Teams

Before deploying a normalizer, verify:

- [ ] Normalizer has correct function signature (accepts raw_output, action_contract)
- [ ] Normalizer NEVER raises exceptions (always returns NormalizationResult)
- [ ] Normalizer handles None input gracefully
- [ ] Normalizer handles unexpected type/structure gracefully
- [ ] Normalizer includes warnings for suspicious conditions
- [ ] Normalized output validates against output_schema in 100% of test cases
- [ ] All required fields are present in normalized output (never None for required fields)
- [ ] Test harness passes (happy path + edge cases)
- [ ] Normalizer does not perform I/O or call external services
- [ ] Normalizer code is readable and includes comments on mapping logic
- [ ] Backend output examples included in code documentation
- [ ] Normalizer has been tested against real backend output (not just synthetic data)
- [ ] Performance: normalizer completes in <100ms for typical input
- [ ] Memory: normalizer doesn't hold references to large inputs after completion


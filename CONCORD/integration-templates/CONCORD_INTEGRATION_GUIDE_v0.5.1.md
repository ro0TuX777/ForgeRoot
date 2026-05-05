# CONCORD Integration Guide — v0.5.1 Application-Agnostic Edition

**Status:** Normative Integration Guidance | **Version:** v0.5.1 | **Date:** April 2026  
**Audience:** Any AI agent or development team tasked with wiring a host application for CONCORD governance  
**Prerequisite Reading:** 
  - CONCORD v0.3 Core Specification
  - CONCORD v0.5 Admission Pipeline Specification  
  - CONCORD v0.5.1 JSON Schema Adoption
  - CONCORD v0.5.1 Receipt Validation Specification

---

## Part 1: Conceptual Foundation

### 1.1 What You're Building

You are building a **governed execution pipeline** — a new entry surface that sits between agent consumers and your application's existing business logic.

```
┌────────────────────────────────────────────────────────────┐
│                  Your Application                           │
│                                                              │
│  ┌──────────────────────┐     ┌──────────────────────────┐ │
│  │ Existing Surface      │     │ CONCORD Governed Surface  │ │
│  │ ──────────────────    │     │ ─────────────────────────│ │
│  │ • HTML/Web UI         │     │ • CONCORD admission      │ │
│  │ • Human workflows     │     │ • Intent-driven          │ │
│  │ • Session management  │     │ • Structured I/O         │ │
│  │ • Error pages         │     │ • Governed receipts      │ │
│  └────────────┬──────────┘     └──────────────┬───────────┘ │
│              │                               │               │
│              │    ┌──────────────────────┐   │               │
│              └───→│  Business Logic Layer │←──┘               │
│                   │ ──────────────────── │                    │
│                   │ • Actual operations  │                    │
│                   │ • Data access        │                    │
│                   │ • External calls     │                    │
│                   └──────────────────────┘                    │
└────────────────────────────────────────────────────────────┘
```

You are **NOT**:
- Modifying existing routes, templates, or UI code
- Changing how humans interact with the application
- Building a thin wrapper over existing endpoints
- Replicating business logic

You ARE:
- Building a new API surface for agents
- Running all agent requests through CONCORD's admission pipeline
- Extracting and normalizing outputs for agent consumption
- Returning structured, governed receipts

### 1.2 Key Principle: The Admission Pipeline Is Mandatory

**Every action flows through the admission pipeline. No exceptions.**

When you skip the pipeline to "speed things up," you create a governance bypass. Your integration silently breaks. This is not a feature or optimization — it's a security violation.

The pipeline exists for three reasons:
1. **Trust enforcement** — verify the agent has permission to do this
2. **Budget enforcement** — prevent resource exhaustion
3. **Safety enforcement** — invoke guards to check preconditions

All three matter. The admission pipeline is non-negotiable.

---

## Part 2: Integration Sequence

Follow these steps **in order**. Each step builds on the previous.

### Step 1: Application Audit & Capability Inventory

**Goal:** Identify every discrete capability your application offers.

**Procedure:**

1. **List all business operations** the application can perform
   - Don't overthink it. List them as actions: "scan document," "convert format," "validate data," "generate report"

2. **For each operation, document:**

   | Field | What to Document | Example |
   |---|---|---|
   | **Capability Name** | Use `family.verb` format | `document.scan_pdf`, `document.convert_format`, `report.generate` |
   | **Business Purpose** | 1-2 sentences | "Analyzes a PDF document for violations of coding standards" |
   | **Backend Function** | The actual code entry point | `app.security.Scanner.run_static_analysis()` |
   | **Input Parameters** | What it needs | File path (str), max depth (int), extract images (bool) |
   | **Output Data** | What it returns (raw form) | HTML report table, JSON result dict, file path |
   | **Execution Time** | Typical duration | ~5 seconds for 100-page PDF |
   | **Resource Cost** | Estimated compute/API usage | CPU usage, API calls consumed |
   | **Constraints** | Business rules, preconditions | "Must have valid config", "Target file must be readable" |
   | **Side Effects** | Does it mutate state? | "Writes converted file to disk" |
   | **Error Modes** | What can go wrong? | "File not found", "Invalid format", "Permission denied" |

3. **Organize into groups** (optional but helpful):
   - Read-only: scanning, analyzing, reporting, querying
   - Safe mutations: testing, staging, dry-run
   - Risky mutations: production changes
   - Compensating: undo operations

**Deliverable:** A spreadsheet or document with 1 row per capability.

**Example (for a Document Processing Application):**

| Capability Name | Backend Function | Inputs | Output | Trust | Cost |
|---|---|---|---|---|---|
| `doc.scan_pdf` | `Scanner.analyze_pdf()` | path:str, max_pages:int | PDF analysis result | T1 | 100 |
| `doc.extract_text` | `TextExtractor.extract()` | path:str, encoding:str | Extracted text | T1 | 50 |
| `doc.convert_format` | `Converter.convert()` | src:str, format:str | Converted file path | T1 | 75 |
| `doc.validate_schema` | `Validator.validate()` | path:str, schema:str | Validation result | T1 | 40 |
| `config.update` | `ConfigManager.update()` | key:str, value:any | Confirmation | T3 | 10 |

### Step 2: Define ActionContracts

**Goal:** Formally describe each capability in CONCORD's terms.

**For each capability from Step 1, create an ActionContract:**

```json
{
  "action_name": "document.scan_pdf",
  "action_family": "read",
  "minimum_trust_tier": 1,
  "cost": 100,
  "cost_category": "analysis",
  
  "input_schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
      "pdf_path": {
        "type": "string",
        "description": "Absolute or relative path to PDF file"
      },
      "max_pages": {
        "type": "integer",
        "description": "Maximum pages to analyze (0 = unlimited)",
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
  },
  
  "output_schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
      "pages_analyzed": {
        "type": "integer",
        "description": "Number of pages processed"
      },
      "text_content": {
        "type": "string",
        "description": "Extracted text from all pages"
      },
      "confidence_score": {
        "type": "number",
        "minimum": 0,
        "maximum": 1,
        "description": "Confidence in text extraction"
      },
      "images_extracted": {
        "type": "integer",
        "description": "Number of images extracted"
      },
      "warnings": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Processing warnings"
      }
    },
    "required": ["pages_analyzed", "text_content", "confidence_score"],
    "additionalProperties": false
  },
  
  "guards": ["service_healthy", "file_accessible", "perm_sufficient"],
  
  "idempotent": true,
  "idempotency_key": "pdf_path"
}
```

**Use JSON Schema (Draft 2020-12) for all schemas.** See [JSON Schema Adoption](CONCORD_v0.5_JSON_Schema_Adoption.md) for specification.

**Key decisions for each action:**

1. **Minimum trust tier** — what's the lowest trust level that should be able to do this?
   - T0 = sandbox (read-only queries only)
   - T1 = limited (non-production operations)
   - T2 = trusted (production reads)
   - T3 = high-trust (production mutations)
   - T4 = autonomous (can make unreviewed decisions)

2. **Guards** — what preconditions must be true?
   - `service_healthy` — is the backend responding?
   - `resource_accessible` — can you access the target?
   - `perm_sufficient` — does the agent have permission?
   - Others specific to your domain

3. **Idempotency** — is this operation safe to retry?
   - If yes, specify what makes it idempotent (usually input #, file name, or id)

4. **Output schema** — what does the agent need to know?
   - Use meaningful field names
   - Include counts, status indicators, extracted values
   - Do NOT just return markup or log output

**Deliverable:** One `.json` file per ActionContract in a registry.

### Step 3: Build the Guard Registry

**Goal:** Implement the precondition checks that guards declare.

For each guard name declared on any action, write a function that actually checks it:

```python
# guards.py

def service_healthy(parameters, session, action_contract):
    """
    Check if the document processing service is responding.
    """
    try:
        response = requests.get("http://localhost:9000/health", timeout=2)
        if response.status_code == 200:
            return {
                "passed": True,
                "guard_name": "service_healthy"
            }
        else:
            return {
                "passed": False,
                "guard_name": "service_healthy",
                "reason": f"Service returned {response.status_code}"
            }
    except Exception as e:
        return {
            "passed": False,
            "guard_name": "service_healthy",
            "reason": f"Health check failed: {str(e)}"
        }

def file_accessible(parameters, session, action_contract):
    """
    Check if the target file exists and is readable.
    """
    path = parameters.get("pdf_path")
    if not path:
        return {
            "passed": False,
            "guard_name": "file_accessible",
            "reason": "No pdf_path parameter provided"
        }
    
    try:
        if not os.path.exists(path):
            return {"passed": False, "guard_name": "file_accessible", 
                   "reason": f"File not found: {path}"}
        if not os.access(path, os.R_OK):
            return {"passed": False, "guard_name": "file_accessible",
                   "reason": f"File not readable: {path}"}
        
        return {"passed": True, "guard_name": "file_accessible"}
    except Exception as e:
        return {"passed": False, "guard_name": "file_accessible",
               "reason": str(e)}

def perm_sufficient(parameters, session, action_contract):
    """
    Check if the agent's trust tier is sufficient for this action.
    """
    # This is typically handled by the TrustGate stage,
    # but you can add domain-specific permission checks here
    return {"passed": True, "guard_name": "perm_sufficient"}

# Registry
GUARD_REGISTRY = {
    "service_healthy": service_healthy,
    "file_accessible": file_accessible,
    "perm_sufficient": perm_sufficient,
}
```

**Startup validation:** When your pipeline initializes, verify that every guard declared on any action has a registry entry. Missing guards are a deploy-time failure.

```python
def validate_guards_are_registered(action_contracts, guard_registry):
    """Verify all declared guards have implementations."""
    missing = set()
    for action in action_contracts:
        for guard_name in action.get("guards", []):
            if guard_name not in guard_registry:
                missing.add(guard_name)
    
    if missing:
        raise RuntimeError(f"Guards declared but not registered: {missing}")
```

### Step 4: Build the Executors

**Goal:** Translate CONCORD intents into backend function calls and handle errors.

An executor has three responsibilities:
1. **Parameter translation** — map CONCORD parameters to backend parameters
2. **Exception handling** — catch backend exceptions and classify them
3. **Result structure** — return a structured ExecutionResult

```python
# executors.py

EXECUTION_EXCEPTIONS_MAP = {
    FileNotFoundError: ("FILE_NOT_FOUND", "recheck"),
    PermissionError: ("PERMISSION_DENIED", "escalate"),
    TimeoutError: ("EXECUTION_TIMEOUT", "retry"),
    ValueError: ("INVALID_PARAMETERS", "recheck"),
    Exception: ("EXECUTION_FAILED", "report"),
}

@dataclass
class ExecutionResult:
    success: bool
    result_summary: Optional[dict] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    zero_cost: bool = False

def execute_scan_pdf(parameters, session, action_contract):
    """
    Execute the PDF scan action.
    
    Translates CONCORD parameters to backend call,
    handles exceptions, returns structured result.
    """
    try:
        # Parameter translation
        pdf_path = parameters["pdf_path"]
        max_pages = parameters.get("max_pages", 0)
        extract_images = parameters.get("extract_images", False)
        
        # Call backend
        scanner = PDFScanner()
        raw_output = scanner.analyze_pdf(
            path=pdf_path,
            max_pages=max_pages or None,
            extract_images=extract_images
        )
        
        # Return structured result (normalizer will transform this)
        return ExecutionResult(
            success=True,
            result_summary=raw_output
        )
    
    except FileNotFoundError as e:
        return ExecutionResult(
            success=False,
            error_code="FILE_NOT_FOUND",
            error_detail=str(e)
        )
    
    except Exception as e:
        # Catch-all for unclassified exceptions
        return ExecutionResult(
            success=False,
            error_code="EXECUTION_FAILED",
            error_detail=str(e)
        )

# Executor registry
EXECUTORS = {
    "document.scan_pdf": execute_scan_pdf,
    "document.convert_format": execute_convert_format,
    # ... more executors
}
```

**Key rules:**
- Executors MUST NOT return unstructured HTML or raw log output
- Executors MUST catch ALL exceptions and classify them
- Executors return `ExecutionResult` with `result_summary` (raw backend output)
- Executors do NOT normalize output — that's the normalizer's job
- Executors do NOT update the budget — that's ReceiptMinting's job

### Step 5: Build Normalizers

**Goal:** Transform backend output into structured, schema-conformant data.

See [Normalizer Specification](../integration-templates/NORMALIZER_SPECIFICATION.md) for comprehensive guidance.

**Example normalizer:**

```python
# normalizers.py

@dataclass
class NormalizationResult:
    normalized: Optional[dict]
    success: bool
    warnings: List[str]
    error_detail: Optional[str] = None

def normalize_scan_pdf(raw_output, action_contract):
    """
    Transform PDF scanner output to match output_schema.
    """
    result = NormalizationResult(normalized={}, success=True, warnings=[])
    
    try:
        if raw_output is None:
            result.success = False
            result.error_detail = "Backend returned None"
            return result
        
        # Extract fields
        normalized = {
            "pages_analyzed": int(raw_output.get("num_pages", 0)),
            "text_content": str(raw_output.get("extracted_text", "")),
            "confidence_score": float(raw_output.get("extraction_confidence", 0.5)),
            "images_extracted": int(raw_output.get("images_count", 0)),
            "warnings": raw_output.get("processing_warnings", [])
        }
        
        # Validate required fields
        if not normalized["pages_analyzed"]:
            result.warnings.append("No pages were analyzed")
        if not normalized["text_content"]:
            result.success = False
            result.error_detail = "No text content extracted"
            return result
        
        # Clamp confidence score
        normalized["confidence_score"] = max(0, min(1, normalized["confidence_score"]))
        
        result.normalized = normalized
        return result
    
    except Exception as e:
        result.success = False
        result.error_detail = str(e)
        return result

# Normalizer registry
NORMALIZERS = {
    "document.scan_pdf": normalize_scan_pdf,
    "document.convert_format": normalize_convert_format,
    # ... more normalizers
}
```

**Test your normalizers thoroughly.** See Normalizer Specification §5 for test harness template.

### Step 6: Implement the Admission Pipeline

**Goal:** Wire the 11-stage admission pipeline that governs all action execution.

See [Admission Pipeline Specification](../CONCORD_v0.5_Admission_Pipeline_Specification.md) for details. Here's a reference implementation:

```python
# admission_pipeline.py

class AdmissionPipeline:
    def __init__(self, action_registry, guard_registry, executors_registry, 
                 normalizers_registry, budget_ledger):
        self.actions = action_registry
        self.guards = guard_registry
        self.executors = executors_registry
        self.normalizers = normalizers_registry
        self.budget = budget_ledger
    
    def process_intent(self, intent_request):
        """
        Process an intent through the 11-stage pipeline.
        Returns (success: bool, response: dict)
        """
        
        # ① SessionResolution
        session = self._stage_session_resolution(intent_request.session_id)
        if not session:
            return False, {"error_code": "SESSION_NOT_FOUND"}
        
        # ② ActionResolution
        action_contract = self._stage_action_resolution(intent_request.action_name)
        if not action_contract:
            return False, {"error_code": "ACTION_NOT_FOUND"}
        
        # ③ TrustGate
        if not self._stage_trust_gate(session, action_contract):
            return False, {"error_code": "TRUST_INSUFFICIENT"}
        
        # ④ BudgetGate
        if action_contract.get("cost"):
            if not self._stage_budget_gate(session, action_contract):
                return False, {"error_code": "BUDGET_EXCEEDED"}
        
        # ⑤ GuardEvaluation
        if action_contract.get("guards"):
            guard_result = self._stage_guard_evaluation(
                intent_request.parameters, session, action_contract
            )
            if not guard_result["passed"]:
                return False, {"error_code": "GUARD_FAILED", "detail": guard_result}
        
        # ⑥ InputValidation
        validation_result = self._stage_input_validation(
            intent_request.parameters, action_contract
        )
        if not validation_result[0]:
            return False, {"error_code": "INVALID_PARAMETERS", "detail": validation_result[1]}
        
        # ⑦ IdempotencyCheck
        if intent_request.get("idempotency_key"):
            if self._stage_idempotency_check(intent_request.idempotency_key):
                return False, {"error_code": "IDEMPOTENCY_CONFLICT"}
        
        # ⑧ IntentCreation
        intent_id = self._stage_intent_creation(intent_request, session, action_contract)
        
        # ═══════════════════ ADMISSION BOUNDARY ════════════════════
        
        # ⑨ Execution
        executor = self.executors[action_contract["action_name"]]
        execution_result = executor(intent_request.parameters, session, action_contract)
        
        # ⑩ OutputNormalization
        if action_contract.get("output_schema"):
            normalizer = self.normalizers[action_contract["action_name"]]
            norm_result = normalizer(execution_result.result_summary, action_contract)
            if not norm_result.success:
                return False, {"error_code": "OUTPUT_NORMALIZATION_FAILED"}
            normalized_output = norm_result.normalized
        else:
            normalized_output = execution_result.result_summary
        
        # ⑪ ReceiptMinting
        receipt = self._stage_receipt_minting(
            intent_id, normalized_output, action_contract, session
        )
        
        return True, {"receipt_id": receipt.receipt_id, "result": receipt.result_summary}
    
    # Stage implementations (pseudocode)
    def _stage_session_resolution(self, session_id):
        session = SessionDB.get(session_id)
        if not session or session.expired:
            return None
        return session
    
    def _stage_action_resolution(self, action_name):
        return self.actions.get(action_name)
    
    def _stage_trust_gate(self, session, action_contract):
        return session.agent_class.trust_tier >= action_contract["minimum_trust_tier"]
    
    def _stage_budget_gate(self, session, action_contract):
        return self.budget.has_sufficient_budget(session, action_contract["cost"])
    
    def _stage_guard_evaluation(self, parameters, session, action_contract):
        for guard_name in action_contract.get("guards", []):
            guard_func = self.guards[guard_name]
            result = guard_func(parameters, session, action_contract)
            if not result["passed"]:
                return result
        return {"passed": True}
    
    def _stage_input_validation(self, parameters, action_contract):
        # Use JSON Schema validator
        from jsonschema import validate
        try:
            validate(instance=parameters, schema=action_contract["input_schema"])
            return (True, None)
        except Exception as e:
            return (False, str(e))
    
    def _stage_idempotency_check(self, idempotency_key):
        # Check if receipt exists for this key
        return ReceiptDB.find_by_idempotency_key(idempotency_key) is not None
    
    def _stage_intent_creation(self, intent_request, session, action_contract):
        intent = Intent(
            session_id=session.session_id,
            action_name=intent_request.action_name,
            parameters=intent_request.parameters,
            status="admitted"
        )
        IntentDB.store(intent)
        return intent.intent_id
    
    def _stage_receipt_minting(self, intent_id, result, action_contract, session):
        # Validate result against output_schema
        from jsonschema import validate
        if action_contract.get("output_schema"):
            try:
                validate(instance=result, schema=action_contract["output_schema"])
                validation_passed = True
            except:
                validation_passed = False
        else:
            validation_passed = True
        
        # Deduct cost
        if action_contract.get("cost"):
            self.budget.deduct(session.session_id, action_contract["cost"])
        
        # Create Receipt
        receipt = Receipt(
            intent_id=intent_id,
            result_summary=result,
            validation_passed=validation_passed,
            status="completed"
        )
        ReceiptDB.store(receipt)
        return receipt
```

### Step 7: Implement Planning Endpoints

**Goal:** Provide endpoints agents use to plan and check constraints before submission.

```python
# planning_endpoints.py

@app.route("/operation-context/<action_name>", methods=["GET"])
def operation_context(action_name):
    """
    Return metadata about an action for planning.
    """
    action = ACTION_REGISTRY.get(action_name)
    if not action:
        return {"error": "ACTION_NOT_FOUND"}, 404
    
    session_id = request.headers.get("X-Session-ID")
    session = SessionDB.get(session_id)
    if not session:
        return {"error": "SESSION_NOT_FOUND"}, 401
    
    return {
        "action_name": action["action_name"],
        "action_family": action["action_family"],
        "minimum_trust_tier": action["minimum_trust_tier"],
        "cost": action["cost"],
        "input_schema": action["input_schema"],
        "output_schema": action["output_schema"],
        "guards": action["guards"],
        
        # Dynamic info for the agent
        "agent_can_execute": (
            session.agent_class.trust_tier >= action["minimum_trust_tier"]
        ),
        "remaining_budget": BUDGET_LEDGER.get_remaining(session.session_id),
        "trust_sufficient": (
            session.agent_class.trust_tier >= action["minimum_trust_tier"]
        ),
    }

@app.route("/budget/status", methods=["GET"])
def budget_status():
    """
    Return remaining budget for the session.
    """
    session_id = request.headers.get("X-Session-ID")
    session = SessionDB.get(session_id)
    if not session:
        return {"error": "SESSION_NOT_FOUND"}, 401
    
    ledger = BUDGET_LEDGER.get(session.session_id)
    return {
        "session_id": session_id,
        "total_budget": ledger.total,
        "consumed": ledger.consumed,
        "remaining": ledger.remaining,
        "percent_used": (ledger.consumed / ledger.total * 100) if ledger.total else 0
    }

@app.route("/session/refresh", methods=["POST"])
def session_refresh():
    """
    Extend a session's TTL.
    """
    session_id = request.json.get("session_id")
    extension_ms = request.json.get("extension_ms")
    
    session = SessionDB.get(session_id)
    if not session:
        return {"error": "SESSION_NOT_FOUND"}, 404
    
    old_expires = session.expires_at
    session.expires_at = session.expires_at + timedelta(milliseconds=extension_ms)
    SessionDB.update(session)
    
    return {
        "session_id": session_id,
        "old_expires_at": old_expires,
        "new_expires_at": session.expires_at
    }
```

---

## Part 3: Testing Your Integration

### Governance Tests (Independent of Backend)

Test the admission pipeline in isolation:

```python
# test_governance.py

def test_admission_pipeline_rejects_expired_session():
    """Session expired → SESSION_EXPIRED error."""
    expired_session = SessionStore.create_expired()
    result = pipeline.process_intent(
        IntentRequest(session_id=expired_session.id, action_name="test.action")
    )
    assert result[1]["error_code"] == "SESSION_EXPIRED"

def test_admission_pipeline_rejects_insufficient_trust():
    """Agent tier < action minimum → TRUST_INSUFFICIENT error."""
    session = SessionStore.create_with_tier(T0)  # Sandbox agent
    result = pipeline.process_intent(
        IntentRequest(session_id=session.id, action_name="admin.action")  # Needs T3
    )
    assert result[1]["error_code"] == "TRUST_INSUFFICIENT"

def test_admission_pipeline_rejects_budget_exceeded():
    """Insufficient budget → BUDGET_EXCEEDED error."""
    session = SessionStore.create_with_budget(50)  # 50 units
    result = pipeline.process_intent(
        IntentRequest(session_id=session.id, action_name="expensive.action")  # Costs 100
    )
    assert result[1]["error_code"] == "BUDGET_EXCEEDED"

def test_admission_pipeline_guard_failure():
    """Guard fails → GUARD_FAILED error."""
    session = SessionStore.create()
    # Disable service for this test
    with mock_service_down():
        result = pipeline.process_intent(
            IntentRequest(session_id=session.id, action_name="doc.scan_pdf",
                        parameters={"pdf_path": "/nonexistent.pdf"})
        )
    assert result[1]["error_code"] == "GUARD_FAILED"

def test_admission_pipeline_input_validation_failure():
    """Invalid parameters → INVALID_PARAMETERS error."""
    session = SessionStore.create()
    result = pipeline.process_intent(
        IntentRequest(session_id=session.id, action_name="doc.scan_pdf",
                    parameters={"pdf_path": 123})  # Wrong type
    )
    assert result[1]["error_code"] == "INVALID_PARAMETERS"

def test_receipt_generation_and_cost_deduction():
    """Valid intent → Receipt created, cost deducted."""
    session = SessionStore.create_with_budget(1000)
    with mock_backend_return({"num_pages": 10, "text": "Content", "confidence": 0.9}):
        success, response = pipeline.process_intent(
            IntentRequest(session_id=session.id, action_name="doc.scan_pdf",
                        parameters={"pdf_path": "/test.pdf"})
        )
    
    assert success
    receipt = ReceiptDB.get(response["receipt_id"])
    assert receipt is not None
    assert receipt.result_summary["pages_analyzed"] == 10
    assert session.budget.remaining < 1000  # Cost was deducted
```

### End-to-End Tests (With Backend)

Test real workflows:

```python
# test_end_to_end.py

def test_scan_pdf_workflow():
    """Full workflow: scan PDF → extract text → convert."""
    session = SessionStore.create()
    
    # Step 1: Scan
    success, r1 = pipeline.process_intent(
        IntentRequest(session_id=session.id, action_name="doc.scan_pdf",
                    parameters={"pdf_path": "sample.pdf"})
    )
    assert success
    assert r1["result"]["pages_analyzed"] == 42
    
    # Step 2: Extract (agent decides to extract)
    text_content = r1["result"]["text_content"]
    success, r2 = pipeline.process_intent(
        IntentRequest(session_id=session.id, action_name="doc.extract_text",
                    parameters={"text": text_content})
    )
    assert success
```

---

## Part 4: Integration Validation Checklist

Use this before declaring integration complete:

**Capability Audit:**
- [ ] Every backend operation has a corresponding ActionContract
- [ ] `input_schema` uses JSON Schema and correctly describes parameters
- [ ] `output_schema` uses JSON Schema and describes what agents need
- [ ] All `required` fields are truly mandatory
- [ ] All `additionalProperties` constraints are intentional

**Guards & Permissions:**
- [ ] Every declared guard has a registry entry
- [ ] Guards are tested (pass/fail cases)
- [ ] Guards include meaningful failure reasons
- [ ] Trust tiers are assigned consistently

**Executors:**
- [ ] All backend exceptions are caught and classified
- [ ] No backend exceptions escape unclassified
- [ ] Parameter translation is bidirectional documented
- [ ] Executors return structured `ExecutionResult`
- [ ] Executors handle None/invalid inputs gracefully

**Normalizers:**
- [ ] Every action with `output_schema` has a normalizer
- [ ] Normalizers never raise exceptions
- [ ] Normalizers handle missing/malformed input
- [ ] Normalizer output validates against `output_schema` 100% of the time
- [ ] Normalizers are tested (happy path + edge cases)

**Admission Pipeline:**
- [ ] All 11 stages are implemented and tested
- [ ] Pipeline fails-fast on first error
- [ ] No stage creates side effects (except after admission boundary)
- [ ] Cost deduction happens at ReceiptMinting, not earlier
- [ ] All entry points route through pipeline (no shortcuts)

**Receipts & Validation:**
- [ ] Receipts are generated for every action
- [ ] Receipt `result_summary` is validated against `output_schema`
- [ ] Validation failures return `OUTPUT_NORMALIZATION_FAILED`
- [ ] Cost is deducted even on execution failure

**Planning Endpoints:**
- [ ] `/operation-context` returns action metadata + dynamic status
- [ ] `/budget/status` returns remaining budget accurately
- [ ] `/session/refresh` extends session TTL correctly

**Security & Governance:**
- [ ] Trust gates prevent unauthorized actions
- [ ] Budget gates prevent overspending
- [ ] Guards are enforced before execution
- [ ] Audit trail logs all events

**Errors:**
- [ ] All errors include `agent_should` guidance
- [ ] Error responses are structured (not free-form text)
- [ ] Agents can recover from errors based on guidance

**Documentation:**
- [ ] Every ActionContract is documented
- [ ] Normalizers include examples + assumptions
- [ ] Error codes are mapped to recovery strategies
- [ ] Integration guide is application-agnostic

---

## Appendix: Common Integration Mistakes

### Mistake 1: Skipping the Admission Pipeline for Specific Actions

**WRONG:**
```python
# Fast-track for "internal" actions
if action_name.startswith("internal."):
    return EXECUTORS[action_name](params)  # Skip pipeline
```

**RIGHT:**
All actions go through the pipeline. There are no "internal" shortcuts.

### Mistake 2: Not Implementing Output Normalization

**WRONG:**
```python
# Return raw backend output
def execute_scan(params):
    return ExecutionResult(success=True, result_summary=backend.scan(params))
```

**RIGHT:**
```python
# Normalize in the pipeline
def execute_scan(params):
    raw = backend.scan(params)
    return ExecutionResult(success=True, result_summary=raw)

# Then in pipeline:
normalized = normalizer(raw, action_contract)
```

### Mistake 3: Type Coercion in Validation

**WRONG:**
```python
# Convert string to int
parameters["timeout"] = int(parameters.get("timeout", "300"))
# This masks type errors
```

**RIGHT:**
```python
# Validate type, reject if wrong
if not isinstance(parameters.get("timeout"), int):
    return error  # INVALID_PARAMETERS
```

### Mistake 4: Assuming Predictable Backend Output

**WRONG:**
```python
# Assume backend always returns this structure
def normalize(output):
    return {"count": output["results"]["length"]}
```

**RIGHT:**
```python
# Handle variations
def normalize(output):
    if not isinstance(output, dict):
        return NormalizationResult(success=False)
    
    count = output.get("results", {}).get("length")
    if count is None:
        return NormalizationResult(success=False, error_detail="Missing count")
    
    return NormalizationResult(normalized={"count": count}, success=True)
```


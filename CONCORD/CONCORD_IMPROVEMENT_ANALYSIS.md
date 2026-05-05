# CONCORD Architecture Improvements — Integration Analysis

**Date:** April 2026  
**Audience:** CONCORD development team, future integration partners  
**Purpose:** Map the 7 structural limits from the SAM integration to root architectural causes and propose concrete improvements for backend logic recognition and leverage  

---

## Executive Summary

The SAM integration exposed 7 structural limits, but analysis reveals only **2–3 are true architectural gaps**. The remaining 4–5 stem from:
- **Integration agent misunderstanding** of the governed execution model
- **Missing normative guidance** that CONCORD should provide explicitly
- **Design-by-assumption** rather than explicit contracts in the spec

Most critically: **the integration agent never wired the admission pipeline.** CONCORD governs Session creation but never governs action execution because Intents are never created; SAM's ticket system drives execution invisibly to CONCORD.

**The core insight for backend logic recognition:** CONCORD's strength is making implicit backend capabilities explicit through three artifacts:
1. **ActionContracts** that accurately describe what the backend can do
2. **Executors** that normalize backend outputs into structured shapes agents can consume
3. **The admission pipeline** that enforces governance as actions flow through the system

When these three are wired correctly, agents can discover, plan, and leverage backend logic at scale. The SAM integration wired only the first incompletely; it skipped the second and third entirely.

---

## Part 1: Diagnosis of the 7 Structural Limits

### Limit #1: CONCORD Governs Session but Not Operations — No Intents/Receipts Flow

**What happened:** CONCORD created a Session for the SAM integration, but subsequent actions never flowed through the CONCORD admission pipeline. SAM's internal ticket system performed all work invisibly. CONCORD recorded the session but had no record of what actions had been attempted, their results, or budget consumption.

**Root cause:** The integration agent misunderstood CONCORD's execution model.

**Analysis:**
- CONCORD's design is: every action flows through the admission pipeline, producing an Intent and a Receipt
- The integration agent instead wired SAM's ticket system as a parallel execution engine
- Sessions existed but were decorational — they had no Intents or Receipts bound to them
- The integration agent treated CONCORD as a governance wrapper, not an **execution coordinator**

**This is an architectural clarity problem**, not an architectural bug in CONCORD. The spec should be explicit: **CONCORD owns the execution path. Actions do not execute outside the pipeline.**

**What CONCORD must clarify:**
1. State explicitly in the Core Specification: "CONCORD governance applies to ALL work performed on behalf of an agent. Actions that bypass the admission pipeline are a governance violation."
2. Provide a normative section in the Integration Guide: "Your executor is the sole gateway to the backend. No business logic may be invoked except through the executor."
3. Define a `GoverningAgent` obligation: integrations MUST produce an Intent for every action the agent attempts (even read-only actions).

**Proposed fix:**
- Add a section to the Integration Guide titled **"The Admission Pipeline Is Non-Negotiable"** that explains the execution model with a concrete example showing both the wrong way (direct backend call) and the right way (through the pipeline).

---

### Limit #2: SAM's Capabilities Invisible to CONCORD's Registry — 5 Ticket Types, 23 Skills, 20 Autonomous Actions

**What happened:** SAM had 5 ticket types (e.g., `scan_ticket`, `report_ticket`), 23 skills (e.g., `static_analysis_skill`, `pdf_export_skill`), and 20 autonomous actions (e.g., `ticket.create`, `ticket.resolve`). None of these appeared in CONCORD's ActionContract registry. CONCORD had no knowledge of what SAM could do.

**Root cause:** The capability audit (Camp 2 §2.2 in the lessons doc) was never performed.

**Analysis:**
- The Integration Guide already mandates a capability audit (§3.1)
- The integration agent skipped it, assuming the ticket system was an implementation detail
- No one built ActionContracts for SAM's 5 ticket types or 23 skills
- CONCORD had no mechanism to enumerate what had NOT been registered (it only knows about registered contracts)

**This is a failure of integration discipline**, not a CONCORD architectural failure. However, CONCORD could provide better tools to prevent this:

**What CONCORD must provide:**
1. A **Capability Audit Checklist** and **validation tool** that integration agents use before declaring the integration complete
2. An endpoint: `/action/discover` that allows post-hoc scanning of what ActionContracts exist in a given integration
3. A security gate: integration endpoints should require explicit registration of ALL ActionContracts upfront; runtime discovery of new, unregistered actions should trigger warnings

**Proposed fix:**
- Add a **"Capability Audit Validation Checklist"** section to the Integration Guide (Camp 2 §3.11) that covers:
  - Every domain capability has a corresponding ActionContract
  - Every ActionContract is registered in both the admission pipeline AND queryable via the discovery endpoint
  - A sample audit script that verifies the mapping
- Define an `ActionRegistry.validate()` method in the spec that checks for orphaned backend capabilities

---

### Limit #3: Tool Schema Is Type-Agnostic — Refactor Arriving with No Target_Files, Github_Audit with No Repo_URL

**What happened:** Tool schemas (presumably OpenAI function schemas or similar) defined parameters without types or required-field enforcement. A `refactor` tool arrived with no `target_files` parameter; a `github_audit` tool arrived with no `repo_url`. The integration tried to execute with missing parameters and crashed.

**Root cause:** The input_schema was not validated in the admission pipeline.

**Analysis:**
- This is explicitly addressed in the Admission Pipeline Specification (stage ⑥ — InputValidation)
- The integration agent implemented stage ⑥ but did not enforce type checking or required-field validation
- The OpenAI-style tool schema was not translated into CONCORD's `input_schema` concept with proper constraints
- No validation occurred at all

**This is partly architectural (CONCORD's input_schema format is under-specified) and partly integration (the integration agent didn't implement the stage).**

**What CONCORD must provide:**
1. Adopt **JSON Schema** (draft 2020-12) as the normative format for `input_schema` and `output_schema`
   - This moves away from ambiguous custom formats
   - Gives integration agents a well-known validation library
2. Provide a reference validation implementation (in pseudocode or multiple languages)
3. Explicitly specify in the Admission Pipeline: "InputValidation MUST use a JSON Schema validator. Field-level errors (missing required fields, type mismatches) MUST be returned in the INVALID_PARAMETERS error response."

**Proposed fix:**
- Update the Error Catalog with a revised INVALID_PARAMETERS response structure:
  ```json
  {
    "code": "INVALID_PARAMETERS",
    "severity": "moderate",
    "agent_should": "recheck",
    "detail": {
      "missing_required_fields": ["target_files", "repo_url"],
      "invalid_fields": [
        {
          "field": "timeout_seconds",
          "expected_type": "integer",
          "received_type": "string",
          "received_value": "300"
        }
      ],
      "validation_hints": ["See OperationContext for this action for schema details"]
    }
  }
  ```
- Require all new ActionContracts to use JSON Schema for input_schema and output_schema
- Deprecate legacy custom schema formats

---

### Limit #4: Flow Is Inverted — SAM's Speech Drives Ticket Creation Instead of Agents Submitting Governed Intents

**What happened:** SAM's autonomous decision-making drove the creation of tickets (action requests), which then invoked backend work. The flow was: SAM speaks → ticket created → work executed. CONCORD instead expects: agent submits Intent → pipeline governs → executor handles → Receipt returned.

**Root cause:** Misalignment of the agent-to-system communication model.

**Analysis:**
- SAM was built for reactive, conversational operation (respond to human input)
- CONCORD is built for proactive, structured operation (agent submits governed, pre-planned intents)
- The integration wired SAM's conversational model to CONCORD's session layer but never to CONCORD's execution layer
- This is not a bug in either system; it's a design impedance mismatch

**This is precisely the problem CONCORD is designed to solve:** retooling conversational/reactive systems for agent-driven execution. The integration failed at this fundamental retooling step.

**What CONCORD must clarify:**
1. Define what "agent-driven execution" means in the Core Specification
2. Provide a section in the Integration Guide on retrofitting reactive systems: **"Transforming Reactive Systems for Agent-Driven Execution"** that covers:
   - How to decompose reactive decision-making into explicit Intents
   - How to map the system's internal state machine to CONCORD's governed slots (admitted → executing → receipted)
   - How to handle mid-workflow state transitions in reactive systems

**Proposed fix:**
- Add a new section to the Integration Guide: **"Case Study: From Reactive to Governed"** that walks through:
  1. The wrong way: Let the system continue reactive decision-making, just log it to CONCORD (what SAM did)
  2. The right way: Expose decision points as explicit ActionContracts; have the system await agent Intent before proceeding
  3. Concrete examples of refactoring a ticket system from autonomous-ticket-creation to intent-based-execution

---

### Limit #5: No Structured Output Contract — Agents Get Prose, Not Receipts

**What happened:** When actions completed, the integration returned raw, unstructured output — prose strings, nested dicts, HTML fragments. Agents received data they couldn't parse. Without structured output_schema compliance, agents couldn't build reliable decision-making on top of action results.

**Root cause:** Output normalization was never implemented.

**Analysis:**
- The Integration Lessons (Camp 2 §2.5) identifies output normalization as **"the highest-value work in the entire integration."**
- The integration agent skipped it or treated it as optional
- Without structured output, agents received information they could not machine-parse
- The fundamental contract — Receipt.result_summary conforming to output_schema — was broken

**This is an integration discipline failure**, but CONCORD can make it harder to skip:

**What CONCORD must provide:**
1. Make `output_schema` a **required field** on every ActionContract (not optional)
   - If an action has output, it MUST have an output_schema
   - If it truly has no output, explicitly declare `output_schema: { "type": "null" }`
2. Add validation to the ReceiptMinting stage (⑪) that enforces result_summary conformance to output_schema
   - If conformance fails, return `OUTPUT_NORMALIZATION_FAILED` error
   - The action may still have executed successfully, but the governance contract is broken
3. Provide a Receipt validator in the spec (pseudocode or reference implementation)

**Proposed fix:**
- Update the error catalog to promote `OUTPUT_NORMALIZATION_FAILED` from an internal error to a front-facing error code:
  ```json
  {
    "code": "OUTPUT_NORMALIZATION_FAILED",
    "severity": "elevated",
    "agent_should": "report",
    "detail": {
      "action_name": "scan.static_analysis",
      "expected_schema": { "type": "object", "properties": { "violations_count": { "type": "integer" } } },
      "received_output": "<html><body>Scan complete: 42 violations</body></html>",
      "normalization_error": "Could not extract violations_count from HTML output"
    }
  }
  ```
- Add a section to the Integration Guide: **"Output Normalization Is Non-Negotiable"** that emphasizes this is where agents' ability to reason about results comes from. Without it, integration is theater.
- Require normalizer implementations to be tested independently (see Integration Lessons Camp 2 §2.10)

---

### Limit #6: Evolutionary Center Has No Agent-Accessible REST Equivalent

**What happened:** The integration referenced an "Evolutionary Center" — presumably a SAM component that learns and evolves over time. But there was no REST API or agent-accessible interface to query its state, request evolution, or understand what it had learned. Agents could not interact with this subsystem.

**Root cause:** The "Evolutionary Center" was an internal SAM component not designed for external guidance.

**Analysis:**
- This limit appears specific to SAM's architecture, not a general CONCORD problem
- However, it exposes a pattern: agent-driven systems often have components (learning systems, optimization engines, policy stores) that are internal and invisible to external consumers
- CONCORD doesn't currently specify how to handle such hidden components

**This is a **design pattern** that CONCORD should document:**

**What CONCORD must provide:**
1. A section in the Integration Guide: **"Exposing Internal Components for Agent Guidance"** that covers:
   - Identifying internal components that agents should be able to influence
   - Creating ActionContracts that wrap internal subsystem interactions (e.g., `evolution.request_optimization`, `learning.query_model_state`)
   - How to implement guards that enforce safe interactions with these components
2. Define a pattern for **system-introspection actions** (read-only queries on system state) that agents can use for planning

**Proposed fix:**
- Add a new ActionContract family: `introspect.*` for querying internal system state
- Define guards for introspection (e.g., `requires_read_permission`)
- Provide examples of wrapping opaque subsystems (ML models, optimization engines, policy stores) as queryable objects through ActionContracts

---

### Limit #7: Model-Layer Compatibility Constrains Tool Call Reliability

**What happened:** The integration involved calling OpenAI-compatible APIs with CONCORD-structured input. Some model layers did not reliably parse the structured schemas or respond with the expected structure. Tool calls sometimes failed silently or returned malformed results.

**Root cause:** Impedance mismatch between CONCORD's structured contracts and model-layer expectations.

**Analysis:**
- This is a **model-layer issue**, not a CONCORD architecture issue
- Modern LLM APIs (OpenAI, Anthropic, Together, etc.) have different function-calling schemas and reliability characteristics
- CONCORD should not try to solve model-layer issues
- However, CONCORD should provide guidance on handling model-layer failures

**What CONCORD should do:**
1. Acknowledge this is outside CONCORD's scope but provide mitigation strategies
2. In the Integration Guide, add a section: **"Handling Model-Layer Incompatibilities"** covering:
   - Type mismatches in tool schema translation
   - Incomplete parameter inference (model doesn't fill all required fields)
   - Retry strategies for tool calls that succeed structurally but fail semantically
3. Define a `TOOL_GENERATION_FAILED` error code that bridges model-layer failures to agent-facing error responses

**Proposed fix:**
- Document in Integration Guide Camp 2 §2.11: "Model-Layer Robustness" with guidance on:
  - Validating model-generated intents at admission time (catching malformed outputs before execution)
  - Fallback strategies (if a call fails, what does the agent see?)
  - Testing strategy: validate tool schemas against multiple model versions before release

---

## Part 2: Root Cause Summary

| Limit # | Limit | Root Cause | Type | CONCORD Action |
|---|---|---|---|---|
| 1 | No Intents/Receipts flow | Integration agent bypassed pipeline | Integration discipline | Clarify that pipeline is mandatory |
| 2 | Capabilities invisible | Capability audit skipped | Integration discipline | Provide audit tools and discovery endpoints |
| 3 | Schema type-agnostic | Input validation not enforced | Architecture + Integration | Adopt JSON Schema, require validation |
| 4 | Flow inverted | Reactive vs. governed mismatch | Design pattern | Document reactive→governed transformation |
| 5 | No output contract | Output normalization skipped | Integration discipline | Make output_schema required, enforce Receipt conformance |
| 6 | Internal components invisible | SAM-specific design | Pattern | Document internal component exposure pattern |
| 7 | Model-layer incompatibility | LLM API variation | Out of scope | Document mitigation strategies |

**Breakdown:**
- **True architectural gaps:** #3 (schema format), partially #5 (enforcement)
- **Integration discipline failures:** #1, #2, #5 (could be prevented with stronger guidance)
- **Design pattern gaps:** #4, #6 (need documentation)
- **Out of scope:** #7 (model-layer issue)

---

## Part 3: Concrete Improvements for Backend Logic Recognition & Leverage

### Improvement 1: Explicit Backend Logic Mapping Framework

**What:** Provide a structured process for identifying, cataloging, and exposing backend logic to agents.

**Why:** The SAM integration failed to inventory backend capabilities (Limit #2). Future integrations need a systematic process.

**What CONCORD must add:**

1. **BackendCapability Audit Template** (in Integration Guide Camp 2 §3.1a):
   ```
   Capability Name: [domain.verb format]
   Backend Function: [the actual code entrypoint]
   Inputs: [parameters the backend function accepts]
   Outputs: [what the backend returns]
   Constraints: [business rules, preconditions]
   Agent-Meaningful Output: [what does the agent need to know?]
   Trust Level Required: [minimum AgentClass]
   Estimated Cost: [budget units]
   Guards: [what must be true before execution?]
   Idempotent: [yes/no, and if yes, what makes it safe?]
   Normalizer Complexity: [simple/moderate/complex]
   
   Example filling:
   Capability Name: scan.static_analysis
   Backend Function: app.security.Scanner.run_static_analysis
   Inputs: target_directory (path), max_depth (int)
   Outputs: raw_output = { "violations": [...], "duration_ms": 1234 }
   Constraints: must have scanner config, target must be readable
   Agent-Meaningful Output: { "violation_count": 42, "severity_distribution": {...}, "passed": false }
   Trust Level Required: T1
   Estimated Cost: 100 units
   Guards: ["service_healthy", "target_accessible", "scanner_configured"]
   Idempotent: yes (read-only analysis)
   Normalizer Complexity: moderate (group violations by severity)
   ```

2. **ActionContract Generator** (pseudocode in Integration Guide Camp 2 §3.11):
   ```
   For each audited capability:
     1. Create ActionContract with name from audit
     2. Set input_schema from audit's "Inputs" using JSON Schema
     3. Set output_schema from audit's "Agent-Meaningful Output" using JSON Schema
     4. Declare guards from audit's "Guards"
     5. Set minimum_trust_tier from audit's "Trust Level Required"
     6. Set cost from audit's "Estimated Cost"
     7. Validate: every guard declared must be in the Guard Registry
     8. Store in ActionContract registry
   
   Validation gate: If any audit entry is missing corresponding ActionContract, integration is incomplete.
   ```

3. **Backend Coverage Report** (new endpoint in Runtime Contract Schemas §4):
   ```
   Endpoint: /admin/backend/coverage
   Query: GET
   Response: {
     "total_backend_functions": 42,
     "registered_action_contracts": 38,
     "unregistered_functions": [
       { "name": "internal_heal_check", "reason": "internal use only" },
       { "name": "experimental_feature", "reason": "not yet stabilized" }
     ],
     "missing_normalizers": [...],
     "coverage_percentage": 90.5
   }
   ```

**Impact:** Future integration agents will have a systematic process to ensure no backend logic is left invisible.

---

### Improvement 2: Output Transformation Pipeline Specification

**What:** Formally specify how to transform backend output into agent-meaningful structured data.

**Why:** The SAM integration skipped this (Limit #5), producing unparseable results. This is the moment where agents gain leverage over backend logic.

**What CONCORD must add:**

1. **OutputNormalizer Specification** (in Admission Pipeline Specification §6):
   ```
   Every ActionContract with output_schema != null MUST have a Normalizer.
   
   Normalizer contract:
     Input:  raw_output (whatever the backend returns)
     Input:  action_contract (the ActionContract being executed)
     Output: normalized_result (conforming to action_contract.output_schema)
     Output: warnings (array of issues encountered)
   
   Normalization rules:
     1. Extract structured data from raw_output
     2. Map to output_schema fields by name or semantic equivalence
     3. Handle missing data (absent in raw_output but required in schema):
        - If schema field is optional: omit it
        - If schema field is required: populate with null and add warning
     4. Handle extra data (present in raw_output but not in schema):
        - Ignore it
     5. Type conversions: if raw_output field is string but schema expects integer:
        - Try to convert
        - If conversion fails, add warning and set to null
     6. Throw NO exceptions. Return failed NormalizationResult with warnings.
   
   Validation: Receipt minting fails if normalized result does not conform to output_schema.
   ```

2. **Normalizer Test Harness** (reference implementation in each language):
   ```
   For each normalizer:
     1. Test happy path: real backend output → normalized result passes schema validation
     2. Test missing fields: backend returns partial result → normalizer handles gracefully
     3. Test type mismatches: backend returns wrong type → normalizer converts or warns
     4. Test extra fields: backend returns more data than schema → normalizer ignores
     5. Test error responses: backend returns error object → normalizer captures in warnings
   
   Coverage: 100% of normalizers must pass test harness before integration deployment.
   ```

3. **Code Examples** (in Integration Guide Camp 2 §2.5a):
   ```
   Example: GitHub Audit Scanner
   
   Action: scan.github_audit
   Backend function: github.Scanner.audit_repo(repo_url, check_types)
   Backend returns: {
     "execution_time_ms": 2341,
     "status": "SUCCESS",
     "checks_run": 47,
     "findings": [
       { "check_id": "WEAK_CREDS", "file": "config.py", "line": 42, "severity": 1 },
       { "check_id": "OUTDATED_DEP", "file": "requirements.txt", "line": 12, "severity": 2 }
     ],
     "errors": []
   }
   
   output_schema desired:
   {
     "violation_count": integer,
     "severity_distribution": { "low": int, "medium": int, "high": int },
     "passed": bool,
     "failed_checks": array of { "check_id": str, "file": str, "line": int }
   }
   
   Normalizer:
   ```
   def normalize_github_audit(raw_output, action_contract):
       if raw_output.get("status") != "SUCCESS":
           return {
               "normalized": None,
               "warnings": ["Audit failed: " + raw_output.get("status")]
           }
       findings = raw_output.get("findings", [])
       severity_dist = {"low": 0, "medium": 0, "high": 0}
       failed_checks = []
       
       for finding in findings:
           severity = {1: "low", 2: "medium", 3: "high"}.get(finding["severity"], "medium")
           severity_dist[severity] += 1
           failed_checks.append({
               "check_id": finding["check_id"],
               "file": finding["file"],
               "line": finding.get("line")
           })
       
       return {
           "normalized": {
               "violation_count": len(findings),
               "severity_distribution": severity_dist,
               "passed": len(findings) == 0,
               "failed_checks": failed_checks
           },
           "warnings": []
       }
   ```

**Impact:** Agents will receive structured, parseable results from every action. This enables reliable downstream decision-making.

---

### Improvement 3: Guard as Capability Gatekeeper Framework

**What:** Formalize guards not just as admission pipeline stages but as the mechanism by which agents discover what backend capabilities are currently executable.

**Why:** Limits #2 and #6 stem from hidden backend state. Guards should make that state explicit.

**What CONCORD must add:**

1. **Guard as Introspection Tool** (in Integration Guide Camp 2 §2.6a):
   ```
   Guards serve two purposes:
   1. Safety gate: prevent unsafe executions
   2. Transparency gate: signal to the agent why an action may not be available
   
   When a guard fails, the agent learns about system state. This should be intentional.
   
   Example guard: service_health for an external API
   
   Guard fails with reason: "GitHub API rate limit exceeded, resets at 2026-04-08T14:32:00Z"
   
   Agent learns:
     - The action cannot execute right now
     - The reason (rate limiting)
     - When the constraint will lift (at reset time)
     - Agent can decide to wait, try a different action, or escalate
   ```

2. **Guard Naming Convention Standard** (in Admission Pipeline Specification §2.2):
   ```
   Guard names SHOULD follow a pattern that clearly indicates what system state they check:
   
   Pattern: [component]_[constraint]
   
   Examples:
     - service_healthy — external service responds
     - resource_accessible — file/database/endpoint is reachable
     - config_valid — required configuration is present
     - token_configured — API credentials are in place
     - quota_available — external service quota not exceeded
     - resource_not_locked — no conflicting lease on target
     - review_approved — required human review is complete
     - staging_test_passed — pre-deployment test succeeded
     - quota_available_for_[action] — specific action's quota
   
   This naming convention helps agents understand what they're seeing when guards fail.
   ```

3. **Guard Registry Introspection** (new endpoint in Runtime Contract Schemas §4):
   ```
   Endpoint: /guard/describe/{guard_name}
   GET
   Response: {
     "guard_name": "service_healthy",
     "description": "GitHub API service is responding to health checks",
     "component": "github_integration",
     "failure_modes": [
       {
         "condition": "service is down",
         "signal": "HTTP 5xx from health endpoint",
         "typical_recovery_time_ms": 300000,
         "agent_should": "retry"
       },
       {
         "condition": "rate limited",
         "signal": "rate limit headers present",
         "typical_recovery_time_ms": 3600000,
         "agent_should": "wait_or_retry_later"
       }
     ]
   }
   ```

**Impact:** Guards become tools for agents to understand why capabilities are unavailable and how to work around constraints. Hidden backend state becomes visible.

---

### Improvement 4: Iterative Capability Exposure Pattern

**What:** Formalize the pattern of incrementally exposing backend logic to agents, starting with read-only capabilities and progressing to mutations.

**Why:** The SAM integration tried to expose everything at once and failed. A phased approach reduces risk and allows for tested feedback loops.

**What CONCORD must add (in Integration Guide Camp 2 §3.10a):**

```
Phase 1: Read-Only Introspection
  - Expose all query/scan/analyze capabilities
  - Build and test output normalizers for each
  - Actions: scan.*, report.*, data.query.*
  - No guards needed beyond service_healthy
  - Risk: low
  
Phase 2: Safe Mutations (Reversible)
  - Expose capabilities that modify test/staging resources
  - Build guards to enforce staging-only execution
  - Actions: test.*, stage.*
  - Guards: ["resource_locked_to_staging", "user_approved"]
  - Risk: medium
  
Phase 3: Reversible Production Changes
  - Expose mutations with compensation actions
  - Require ReviewBundle approval (human-in-the-loop)
  - Actions: deploy.*, change.*
  - Guards: ["review_approved", "change_request_locked"]
  - Compensation: defined for each action
  - Risk: elevated
  
Phase 4: Autonomous Production
  - Expose high-confidence mutations that completed phases 1-3
  - Require extensive guard coverage and circuit breakers
  - Actions: auto.*, scheduled.*
  - Guards: [10+ specific preconditions]
  - Risk: high
  
Gate between phases: Pass integration test suite + agent safety review + monitoring baseline established
```

**Impact:** Integrations proceed methodically, catching problems in each phase before escalating to riskier capabilities.

---

## Part 4: Recommendations for CONCORD v0.6

### Must-Have (Blocking Current Integrations)

1. **Adopt JSON Schema for all schemas** — Makes input/output validation unambiguous (Limit #3)
2. **Make output_schema required** — Forces normalizer implementation (Limit #5)
3. **Add validation to Receipt minting** — Enforces output schema conformance (Limit #5)
4. **Document the admission pipeline as mandatory** — Clarify that CONCORD owns execution (Limit #1)

### Should-Have (Prevents Repeating SAM Integration Problems)

1. **Backend Coverage Report endpoint** — Reveals unregistered capabilities (Limit #2)
2. **Capability Audit Template & Guide** — Documents the systematic exposure process (Limit #2)
3. **Output Normalizer Specification & Test Harness** — Defines and validates normalizer quality (Limit #5)
4. **Guard Introspection endpoint** — Makes system state discoverable (Limiting #6)
5. **Reactive-to-Governed transformation guide** — Helps systems like SAM retrofit (Limit #4)

### Nice-to-Have (Improves Agent Experience)

1. **Iterative Capability Exposure pattern** — Reduces risk in rollouts (Improvement #4)
2. **Guard Naming Convention standard** — Improves readability (Improvement #3)
3. **Evolutionary Center pattern documentation** — Guides internal component exposure (Limit #6)

### Out of Scope (Acknowledge, Don't Solve)

1. **Model-layer compatibility** — Provide guidance, but this is LLM vendor problem (Limit #7)

---

## Appendix: Checklist for Future Integration Agents

Use this before declaring integration complete:

- [ ] **Capability Audit:** Every backend capability has a corresponding ActionContract
- [ ] **Action Discovery:** `/admin/backend/coverage` shows 100% coverage or explicit exclusions documented
- [ ] **Input Validation:** All ActionContracts have JSON Schema input_schema; validation tests pass
- [ ] **Executor Wired:** All backend functions accessible **only** through executor; direct calls prohibited
- [ ] **Exception Mapping:** Every exception the backend throws maps to a CONCORD error code
- [ ] **Output Schemas:** All outputs with data have output_schema; schemas are JSON Schema
- [ ] **Normalizers Implemented:** Every action with output_schema has a normalizer; test harness passes 100%
- [ ] **Guards Registered:** Every guard declared on ActionContracts has registry entry + test
- [ ] **Admission Pipeline:** All 11 stages wired and tested; all entry points route through pipeline
- [ ] **Session Lifecycle:** Sessions created, extended, and expired correctly; TTL tests pass
- [ ] **Budget Accounting:** Cost deducted on success, not on admission failure; circuit breakers tested
- [ ] **Receipt Generation:** Every action produces a Receipt; Receipt conforms to action's output_schema
- [ ] **Error Responses:** All errors include `agent_should` guidance; errors tested end-to-end
- [ ] **Governance Tests:** Separate test suite for admission pipeline independent of backend logic
- [ ] **Security Review:** Enforces trust tiers, guards prevent dangerous combinations, audit trails logged
- [ ] **Integration Test:** Happy path for each action type + error paths for each failure mode
- [ ] **Agent Feedback:** Real agent submitted 50+ intents; success rate >95%, errors guided recovery
- [ ] **Documentation:** Integration guide written; all ActionContracts documented for agent consumers

---

## Conclusion

The SAM integration was the first real-world test of CONCORD's ability to retrofit agent governance into existing systems. It revealed not fatal architectural flaws but **discipline gaps** — places where CONCORD's spec is ambiguous or guidance is missing, allowing integration agents to take shortcuts.

The good news: **all seven limits are addressable** through better specification, clearer guidance, and systematic validation. The architectural core of CONCORD (the admission pipeline, the error catalog, the receipt lifecycle) is sound.

The key insight: **CONCORD's power lies in making implicit backend capabilities explicit and governable.** When ActionContracts accurately describe what the backend can do, when executors normalize outputs into structures agents can parse, and when the admission pipeline enforces governance on every action, agents can discover, plan, and execute at scale.

The path forward: invest in the "must-have" improvements (JSON Schema, output schema enforcement, admission pipeline clarity). These block current and future integrations from repeating SAM's mistakes. Then systematize the "should-have" improvements (capability auditing, normalizer specification, guard introspection) so every integration benefits from lessons learned.


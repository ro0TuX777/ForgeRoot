# ForgeLedger Integration Document (FID) Template

> **Purpose:** This template is designed to standardize the integration of third-party agentic applications with the ForgeLedger Governance-Native Evidence Infrastructure. It serves as a living document throughout the integration lifecycle, from initial discovery to final architectural implementation.

---

## Phase 1: Discovery & Requirements
*To be completed by the integrating application's engineering team.*

### 1.1 Agent Workflow & Use Case
* **Primary Workflows:** [Describe the core tasks your AI agents perform, e.g., data retrieval, state modification, content generation.]
* **Agent Autonomy:** [Detail whether agents are purely advisory or take autonomous actions.]
* **Blast Radius:** [Define the worst-case scenario if an agent hallucinates or makes an unauthorized decision.]

### 1.2 Event Emission & Interception Points
*Identify existing middleware, decorators, or event buses that can serve as hooks.*
* **Admission / Authentication:** [Where are agent invocations validated?]
* **Policy Evaluation:** [Where are authorization and resource checks performed?]
* **Model Inferences (LLM Calls):** [Where do prompts leave the system to hit external/local model providers?]
* **Tool / API Execution:** [Where are autonomous tool executions funneled?]
* **Human-in-the-Loop (HITL):** [Where are escalations and human approvals managed?]

### 1.3 Data Sensitivity & Redaction
* **Data Classes:** [List sensitive data types handled, e.g., PII, PHI, proprietary code.]
* **Redaction Capabilities:** [Describe current redaction capabilities vs. reliance on ForgeLedger's ingest-time redaction.]

### 1.4 Tenant Context & Isolation
* **Multi-Tenancy Architecture:** [Describe the tenant model: single, multi, or decentralized mesh.]
* **Residency Requirements:** [List geographic isolation or local-first storage requirements.]

### 1.5 Security & Key Management
* **Secret Management:** [Detail how secrets (e.g., KMS, Vault, environment variables) are managed.]
* **Identity & RBAC:** [Explain how "actors" (both human and agent IDs) are tracked.]

### 1.6 Compliance & Assurance Goals
* **Target Frameworks:** [e.g., SOC 2, HIPAA, NIST CSF, Custom Whitepaper Security Addendums.]
* **Evidence Consumers:** [Who will review the exported evidence packages?]

---

## Phase 2: Architecture & Event Mapping
*To be completed by the ForgeRoot integration team based on Phase 1 responses.*

> **Implementation Note:** A `LedgerEmitter` adapter will be implemented within the target application to format intercepted actions into ForgeLedger events.

### 2.1 Agent Admission
* **Target Component:** [Component identified in 1.2]
* **ForgeLedger Event:** `concord.admission_decision`
* **Implementation:** [Describe the technical hook, e.g., "Hook into the conclusion of the admission pipeline."]
* **Payload Data:** [Required payload: e.g., agent profile, actor ID, allow/deny decision.]

### 2.2 Policy & Resource Evaluation
* **Target Component:** [Component identified in 1.2]
* **ForgeLedger Event:** `forgegate.policy_evaluation`
* **Implementation:** [Describe the technical hook.]
* **Payload Data:** [Required payload: e.g., risk score, execution boundaries.]

### 2.3 Inference Metadata
* **Target Component:** [Component identified in 1.2]
* **ForgeLedger Event:** `warden.llm_call_metadata`
* **Implementation:** [Describe the technical hook.]
* **Payload Data:** [Required payload: e.g., model provider, latency.]
* **⚠️ CRITICAL REDACTION WARNING:** [Specify fields that MUST NOT be emitted, such as raw prompts or PII, based on 1.3.]

### 2.4 Tool Execution
* **Target Component:** [Component identified in 1.2]
* **ForgeLedger Event:** `agent.tool_call`
* **Implementation:** [Describe the technical hook.]
* **Payload Data:** [Required payload: e.g., tool class, sanitized arguments.]

### 2.5 Human-in-the-Loop (HITL)
* **Target Component:** [Component identified in 1.2]
* **ForgeLedger Event:** `agent.human_review_required` / `human.approval_decision`
* **Implementation:** [Describe the technical hook.]
* **Payload Data:** [Required payload: e.g., escalation reason, human decision.]

---

## Phase 3: Security & Data Governance Implementation

### 3.1 Redaction Implementation
* **Configuration:** [Detail the specific JSON paths configured for ForgeLedger ingest-time redaction based on section 1.3.]
* **Receipt Generation:** Confirm mechanism for generating `ledger.redaction_applied` receipts using SHA-256 hashes of original values.

### 3.2 Tenant & Residency Configuration
* **Actor Mapping:** [How ForgeLedger `actor_id` maps to the application's identity system.]
* **Tenant Mapping:** [How ForgeLedger `tenant_id` maps to the application's tenant boundaries.]
* **Ledger Residency:** [Specify the storage mechanism: e.g., local WORM-simulated JSONL vs. Centralized Evidence Bucket.]

### 3.3 Key Management Integration
* **Signing Secret Mechanism:** [Detail how the application's KMS or dynamic keys will seed the ForgeLedger HMAC-SHA256 signing secret.]

---

## Phase 4: Verification & Deliverables
*Standard test plan to prove tamper-evident governance.*

1. **Trigger Action:** Initiate an autonomous agent task (e.g., executing a high-risk tool).
2. **Trace Verification:** Validate that events routed through Admission, Policy Evaluation, Core Engine, and Tool Execution correctly emit to the `LedgerEmitter`.
3. **Redaction Check:** Verify that raw sensitive payloads were replaced with `ledger.redaction_applied` hashes.
4. **Export:** Run the ForgeLedger evidence package generator to export `manifest.json`, `ledger_slice.jsonl`, and the encrypted evidence bundle.
5. **Claim Boundary Labeling:** Ensure the exported package clearly states the required claim boundary: *"Evidence support only. Not a compliance certification."*

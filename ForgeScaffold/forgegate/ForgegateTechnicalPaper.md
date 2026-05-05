# ForgeGate: Deterministic Intent Governance for Agentic Systems

Version: v0.4.0  
Audience: Senior engineering leads, platform/security leads, AI/agent orchestration leads  
Scope: Offline-first, framework-agnostic gate for tool/action governance with auditability, drift controls, and bundle integrity

---

## Abstract

As organizations deploy autonomous or semi-autonomous AI agents, a new failure mode emerges: agents succeed at optimizing measurable proxies (speed, cost, closure rate) while degrading the outcomes the business actually values (trust, retention, safety, compliance). ForgeGate addresses this by introducing a deterministic “intent enforcement layer” between agents and side-effecting actions.

ForgeGate standardizes a minimal, portable contract—ProposedAction + Signals (+ optional BudgetSnapshot) → DecisionRecord—and implements an execution gate that returns ALLOW / ALLOW_WITH_MODS / ESCALATE / DENY. The system is offline-first and orchestrator-agnostic; it includes an IntentBundle packaging format, a local Intent Registry with promotion/rollback workflows, drift reporting with policy thresholds, safety hardening (fail-closed missing signals, payload limits, redaction enforcement), and cryptographic integrity (bundle signing/verification) for governance and auditability.

## 1. Problem Statement
### 1.1 The “agents succeed at the wrong objective” failure mode

Agentic systems are typically deployed with measurable success proxies (e.g., reduce average handle time, reduce escalations, close tickets faster). These proxies are often correlated with desired outcomes but are not equivalent. When an agent is highly competent, it will exploit the proxy ruthlessly—especially when operating at scale and speed.

This creates an “intent gap”: the organization’s purpose, values, and tradeoffs are not machine-actionable, so the agent optimizes what it can measure rather than what the organization intends.

### 1.2 Requirements for an intent layer

To prevent misoptimization at scale, the enforcement layer must be:

Deterministic: repeatable decisions for replay/audit; no hidden stochasticity.

Portable: independent of model vendor, orchestration framework, or tool protocol.

Enforceable: must sit directly on the boundary where side effects occur.

Auditable: must produce structured decision traces explaining why action was allowed/denied/escalated.

Operable: must provide drift reporting and governance workflows.

Offline-first: no required cloud or frontier connectivity; safe for restricted environments.

## 2. System Overview

ForgeGate is a policy/runtime that controls agent action execution. The agent proposes an action; ForgeGate evaluates it against organizational intent and current signals; then it either permits execution, modifies the action, escalates to a human, or denies the action outright.

### 2.1 Core interface

Input:

ProposedAction: normalized description of the intended action, including side-effect classification, risk tier, parameters, and actor metadata.

Signals: machine-readable features that represent situational context (e.g., risk level, classification, sentiment, policy flags).

BudgetSnapshot (optional): deterministic budget state for enforcing spend/time/exception limits.

Output:

DecisionRecord: deterministic decision result with structured reasons, rule IDs triggered, optional modifications, optional escalation payload, and stable hashes for audit/replay.

### 2.2 Decisions

ALLOW: permit action as proposed.

ALLOW_WITH_MODS: permit action with enforced parameter overrides/caps/required steps.

ESCALATE: block action and produce a structured payload for human review/approval.

DENY: reject action, with explicit rule trigger(s).

### 2.3 Execution flow (ASCII)

```
Agent/Orchestrator
        |
        v
  Tool Router / Adapter
        |
        |  ProposedAction + Signals (+ BudgetSnapshot)
        v
    ForgeGate.evaluate
        |
        +--> DecisionRecord (deterministic)
        |
        +--> ALLOW / ALLOW_WITH_MODS -> execute tool
        |
        +--> ESCALATE / DENY -> block tool
        |
        v
   Decision Ledger (JSONL)
```

## 3. Architecture
### 3.1 Major components

Gate Runtime

Deterministic evaluator that enforces constraints, boundaries, budgets, tradeoffs, and action shaping.

Schemas

JSON Schemas for ProposedAction, Signals, DecisionRecord, IntentSpec, BudgetSnapshot, ledger entries, catalogs, registry objects.

IntentBundle

The portable unit of intent adoption: intent spec, catalogs, tests, governance config, docs.

Tool Router Adapter

Offline wrapper that intercepts tool calls, converts them to ProposedAction, invokes the gate, enforces the decision, and writes ledger entries.

Intent Registry

Local-first governance store supporting add/list/promote/rollback/approve flows.

Drift Reporting

CLI that summarizes DecisionRecords and enforces drift thresholds via policy files and exit codes.

Integrity (v0.4.0)

Bundle signing and verification using deterministic manifests and Ed25519 signatures; optional enforcement via validate-bundle --require-signature.

### 3.2 Enforcement point

ForgeGate must be integrated at the last responsible moment: immediately before a tool/action produces side effects (filesystem writes, DB writes, subprocess execution, outbound communications, etc.). If the enforcement point is upstream (e.g., in prompts only), the system is bypassable and not auditable.

## 4. Data Model and Contracts
### 4.1 ProposedAction

ProposedAction is a canonical record with:

action_id: stable action identifier (domain agnostic)

params: action parameters (schema-validated where possible)

side_effect: none/read/write/external_write/irreversible

risk_tier: low/med/high/critical

actor: agent identity + role (researcher/thinker/coder/tester/docs) + autonomy cap

context_refs: references to evidence (IDs/spans), not raw sensitive text

volatile fields (e.g., nonce) are stripped before hashing

### 4.2 Signals

Signals is a typed feature map:

values: signal_name → value

provenance (optional): source/confidence/observed_at (not hashed unless explicitly included)

### 4.3 DecisionRecord

DecisionRecord is the audit artifact:

intent identifiers + versions

decision enum

input_hash (sha256 of canonical inputs)

decision_id (sha256 of intent_version:input_hash)

reasons: triggered rule IDs and summaries; active tradeoff; boundary result; budget state

mods when ALLOW_WITH_MODS

escalation payload when ESCALATE

redactions applied before persistence

### 4.4 IntentSpec

IntentSpec encodes what the organization wants the agent to optimize and what it must never do:

constraints: deny/escalate/approval requirements

boundaries: autonomy caps by action/actor profile

budgets: limits (money/time/exceptions/risk) by window

tradeoffs: conditional objective weight overrides / priority paths

missing-signal behavior (fail-closed) with optional overrides

payload limits and redaction rules (optional governance config)

### 4.5 Catalogs

Action Catalog: defines canonical action_ids and their default risk/side-effect classification.

Signal Catalog: defines signal names, types/enums, and intended provenance.

These support validation and reduce semantic drift across teams.

## 5. Determinism and Replay Safety

ForgeGate is designed to support:

replay of historical decisions

deterministic auditing

deterministic diffs across intent versions

### 5.1 Canonicalization

Inputs are canonicalized using:

stable key ordering

strict JSON (no NaN/Infinity)

normalization of known order-insensitive lists (e.g., context_refs)

stripping of volatile fields (nonce, timestamps, request IDs)

### 5.2 Hashing

input_hash = sha256(canonical({proposed_action_clean, signals.values, budget_snapshot_clean?}))

decision_id = sha256(f"{intent_version}:{input_hash}")

This enables stable indexing and integrity checks across environments.

## 6. Runtime Decision Logic
### 6.1 Evaluation order (deterministic)

Constraints: if triggered → DENY or ESCALATE (stop)

Boundaries: if autonomy exceeded or approval required → ESCALATE (stop)

Budgets: if exceeded → ESCALATE/DENY (stop)

Tradeoffs: select active tradeoff branch (record in DecisionRecord)

Shaping: ALLOW_WITH_MODS (caps, param overrides, required steps)

Emit DecisionRecord + persist to ledger (after redaction)

### 6.2 Fail-closed defaults

Missing required signals referenced by policy → deterministic ESCALATE (policy conflict / human judgment)

Optional explicit overrides exist but must be deliberate and audited

## 7. Operational Artifacts
### 7.1 Decision ledger

ForgeGate appends DecisionRecords to a JSONL ledger format. Drift reporting consumes this ledger to produce:

allow/escalate/deny distributions

top triggered rules

escalation rates by action/role

missing-signal rates

threshold-based exit codes (OK/WARN/CRITICAL)

### 7.2 Drift policy enforcement

A drift policy file defines thresholds for operational stability (e.g., deny spikes, escalation spikes). This enables:

CI gating

cron-based monitoring

pre-release validation

### 7.3 Intent Registry

Local-first store supports:

add intent bundles

promote active intent version

rollback

approval stamps (metadata-level governance)

This provides a minimal governance workflow without requiring centralized services.

### 7.4 Registry promotion flow (ASCII)

```
IntentBundle --> validate-bundle --> registry add
                                      |
                                      v
                           registry promote (active)
                                      |
                         registry rollback / approve
```

## 8. Integrity and Non-Repudiation (v0.4.0)

Phase 4 introduces cryptographic integrity for IntentBundles:

### 8.1 Deterministic bundle manifests

Signing is performed over a deterministic manifest of bundle files:

relative paths

per-file sha256 and size

sorted file list

excluding transient directories and signatures/

### 8.2 Ed25519 signing and verification

sign-bundle emits: bundle.manifest.json + bundle.sig.json

verify-bundle recomputes manifest and validates signature

validate-bundle --require-signature enforces integrity gates for adoption/promotion workflows

This provides a practical integrity primitive for restricted environments and aligns with “intent as code” governance.

Crypto support is optional and installed via:
`pip install -e '.[crypto]'`

### 8.3 Ledger signing + checkpoints

ForgeGate can sign ledgers and emit tamper-evident checkpoints:

```
forgegate sign-ledger ./ledger.jsonl --key ./keys/ed25519_private.pem --checkpoints ./checkpoints --every-n 100
forgegate verify-ledger ./ledger.jsonl --pubkey ./keys/ed25519_public.pem --checkpoints ./checkpoints
```

Checkpoints record ledger head hashes and support fast integrity verification.

## 9. Integration Patterns

ForgeGate avoids coupling to a specific agent framework. Two integration modes are supported:

Generic Tool Router (recommended)

Wrap tool execution in a router that constructs ProposedAction, supplies Signals, invokes gate, enforces decision, writes ledger.

Works with any orchestration: hand-rolled loops, local agent swarms, or other graph frameworks.

LangGraph integration (doc pattern)

Wrap tool nodes/edges with gate calls.

Still uses ProposedAction/Signals normalization for deterministic gating.

## 10. Testing and Quality Gates

ForgeGate is designed to be test-driven and regression-safe:

### 10.1 Scenario tests

Intent unit tests validate:

deny/escalate invariants for constraints

boundary enforcement

budget enforcement

tradeoff activation paths

allow_with_mods shaping correctness

missing-signal fail-closed behavior

redaction enforcement

payload limits deterministic behavior

### 10.2 Determinism tests

Repeated evaluation with identical canonical inputs must produce identical:

decision

input_hash

decision_id

### 10.3 CI gates

CI validates:

installability with dev extras

full pytest suite

bundle validation on example bundles

(v0.4.0) crypto extras in CI for sign/verify tests

## 11. Security Considerations

ForgeGate’s primary security objectives:

prevent unauthorized side effects by default

enforce redaction to avoid leaking sensitive inputs into logs

enforce payload limits to prevent denial-of-service via oversized objects

enforce signature verification to prevent post-approval bundle tampering

Operationally, ForgeGate should be deployed with:

strict filesystem sandboxing for tool execution

subprocess allowlists

explicit segregation of duties for intent approvals

## 12. Roadmap

Short-term evolution (beyond v0.4.0):

Multi-signer bundle/ledger attestations

Replay/diff promotion gates tied to risk thresholds

Execution substrate adapters (optional, remains offline-first)

## Appendix A: Glossary

Intent engineering: encoding organizational goals/values/tradeoffs into machine-actionable constraints and decision logic.

ProposedAction: normalized representation of an agent’s intended action, including parameters and risk classification.

Signals: machine-readable contextual features used for policy decisions.

DecisionRecord: deterministic audit artifact describing the gate’s decision and its rationale.

IntentBundle: versioned package containing intent spec, catalogs, scenarios, and governance settings.

Drift: changes over time in decision distributions, rule triggers, or missing signals indicating misalignment or integration issues.

## Appendix B: Suggested “How to Adopt” Checklist (for senior leads)

Define action taxonomy (Action Catalog) for side-effecting operations.

Define signals that represent risk/context, and implement their extraction deterministically.

Draft IntentSpec constraints/boundaries/budgets/tradeoffs.

Create scenario tests for the highest-risk workflows.

Integrate ForgeGate at tool execution boundaries via Tool Router.

Enable ledger and drift reporting with thresholds.

Require signature verification for promoted bundles in regulated environments.

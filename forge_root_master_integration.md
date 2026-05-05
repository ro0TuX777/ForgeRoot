# ForgeRoot Master Integration Document (MID)

**Status:** Working standard for local / project-level adoption  
**Audience:** AI developers and integrators embedding the ForgeRoot governance and assurance stack into their own codebases and operational harnesses  
**References:** `forge_root_whitepaper_draft.md`, `ResponsefromSAMsDev/forgeledger_integration_template.md`, `ForgeLedger/third_party_integration_questionnaire.md`

---

## 1. Purpose

This document is the **single integration spine** for the ForgeRoot ecosystem. It explains how the control layers fit together, defines a **sequential adoption path** (so teams can ship value before “full stack” maturity), and points to the **ForgeRoot AI Developer Questionnaire** (`forge_root_ai_dev_questionnaire.md`) used to cherry-pick components, define substitutions, and record assurance trade-offs.

ForgeRoot is not one binary: it is a **coordinated lifecycle** from intent admission through governed discovery, deterministic policy, sterile execution, structural governance, and behavioral verification. Integrations should preserve that ordering at boundaries even when some components are deferred or replaced with org-specific implementations.

---

## 2. Ecosystem map (control layers)

| Layer | Component | Role in one sentence |
|-------|-----------|----------------------|
| Admission | **CONCORD** | Fail-fast pipeline: session, trust tier, budget, guards, schema, idempotency—before any side effect. |
| Discovery | **ForgeAtlas** | Semantic capability search with **post-rank** trust and scope filtering (“cannot discover what you cannot admit”). |
| Policy | **ForgeGate** | Deterministic decision on a **concrete** proposed action: allow, deny, escalate, or modify; emits a decision artifact. |
| Runtime | **ForgeHarbor** | Warm-pool, sterile execution via pluggable `EnvironmentProvider` (e.g., containers; path to microVMs/TEEs). |
| Structural | **ForgeScaffold** | Blueprints, blast radius, governed apply pipeline, append-only evidence for structural change. |
| Verification | **Azul** | End-to-end verification ticket: scaffold → harbor → evaluation pipelines → comprehension / dark-code gate → policy. |
| Cross-cutting | **Dark Code Framework** | Layers 1–3 (spec-driven contracts, self-describing systems, human comprehension gates) at infrastructure transitions. |
| Evidence rail | **ForgeLedger** (+ compliance packaging) | Tamper-evident event emission, redaction, export; pairs with the **ForgeLedger Integration Document (FID)** template. |

**Supporting / adjacent** (as referenced in materials and repos): inference governance hooks (e.g., **warden**-class metadata where present), evaluation runners (**ForgeWorks**-class pipelines in verification flows), and control-plane hardening / SIEM mapping (whitepaper Addendum B).

---

## 3. Golden-thread lifecycle (must stay coherent)

ForgeRoot’s strength is **interlocking transitions**. Locally, your harness should preserve this semantic order even if implementations are stubs:

1. **Intent admission** → CONCORD (or documented equivalent).
2. **Governed capability discovery** → ForgeAtlas (or narrowed static catalog + same trust invariant).
3. **Deterministic policy decision** → ForgeGate (or external policy engine with the same separation: model proposes, policy decides).
4. **Sterile runtime** → ForgeHarbor (or another isolated executor with bounded lifecycle).
5. **Structural change governance** → ForgeScaffold when mutating repos/systems (or explicit waiver + risk record).
6. **Behavioral verification & verdict** → Azul-grade pipeline when changes must be proven safe—not only “tests green.”

Anything that skips a layer should be **explicitly captured** in the questionnaire (waivers, compensating controls, timeline to close the gap).

---

## 4. Sequential implementation phases (recommended)

Phases build **dependence order**: upstream layers establish identity, scopes, and evidence before downstream execution and mutation.

### Phase 0 — Integration charter & profile (blocking)

**Goal:** Freeze scope, substitutions, and assurance targets before wiring code.

- Complete `forge_root_ai_dev_questionnaire.md` and circulate the signed-off **integration profile** (components in/out, SaaS/on-prem, latency budget).
- If emitting governance evidence: start a living **FID** using `ResponsefromSAMsDev/forgeledger_integration_template.md` for event mapping responsibilities.
- Document **trust tiers**, **action families**, and **circuit-breaker / kill-switch** semantics you will enforce.

**Exit criteria:** Signed profile + FID skeleton (if using ForgeLedger) + list of interception points.

---

### Phase 1 — Contracts, identity, and evidence baseline

**Goal:** Deterministic contracts and tamper-evident trails before autonomy.

- Stabilize **session / actor identity**, leases, and budget accounts your admission layer will consult.
- Define **JSON Schema** (or equivalent) for intents, receipts, decision records, and tool payloads at boundaries.
- Stand up minimal **ForgeLedger** (or interim structured audit log with a migration path) if accountability is required: see Phase 4 of the FID template for verification habits.

**Exit criteria:** Schemas published; canonical IDs; audit sink reachable from at least one real code path.

---

### Phase 2 — CONCORD (admission)

**Goal:** Every agent path hits a shared fail-fast admission gate.

- Implement the CONCORD pipeline stages relevant to your trust model (subset allowed if questionnaire documents gaps).
- Enforce **sub-second revocation** semantics for session suspension where applicable.

**Exit criteria:** Unauthorized intents cannot reach tool execution or spend budget; revocation test passes.

---

### Phase 3 — ForgeAtlas (governed discovery)

**Goal:** Agents do not receive a flat tool dump; discovery respects trust.

- Integrate semantic ranking **only behind** filtering by `AgentClass`, capability sets, and `TrustTier`.

**Exit criteria:** “Injection/query tricks” cannot surface inadmissible tools in delivered results.

---

### Phase 4 — ForgeGate (deterministic governance)

**Goal:** Separate **proposal** (model / planner) from **verdict** (policy engine).

- Feed proposals + signals + optional budget snapshots into deterministic evaluation.
- Emit stable **DecisionRecord**-class artifacts suitable for hashing and ledger emission.

**Exit criteria:** Policy decisions reproducible given same inputs; no LLM-as-judge on allow/deny.

---

### Phase 5 — ForgeHarbor (sterile execution)

**Goal:** Approved work runs in isolated, recyclable environments with predictable lifecycle.

- Start with provider that matches your infra (container warm pool typical); keep **provider boundary** clean for future microVMs/TEEs.

**Exit criteria:** Parallel tasks do not contaminate; environments terminate and replenish; crashes recycle safely.

---

### Phase 6 — ForgeScaffold (structural assurance)

**Goal:** Controlled mutation with maps, contracts, review packets, evidence.

- Produce blueprint-grade artifacts appropriate to your codebase size; integrate HITL where needed.

**Exit criteria:** Structural changes attach to evidence indices; regressions surfaced by contract/trace, not luck.

---

### Phase 7 — Azul-grade verification (behavioral proof)

**Goal:** Behavioral safety is **shown**, not inferred from green unit tests alone.

- Wire verification tickets: scaffold scoping → harbor provisioning → evaluation pipelines → comprehension / dark-code gate → ForgeGate compatibility.

**Exit criteria:** Scripted scenarios for pass, fail, and `WARNED_DARK_CODE`-class outcomes (see whitepaper Milestone 3).

---

### Phase 8 — Hardening & enterprise interoperability (parallelizable)

**Goal:** Align with organizational security operations.

- Map decision and receipt types to **[OCSF](https://schema.ocsf.io/)**-friendly shapes where required (whitepaper Addendum B).
- Tighten control-plane deployment model (segmentation, stateless evaluators, key rotation).

**Exit criteria:** SIEM ingestion validated on representative workloads; threat exercises for orchestrator misuse documented.

---

## 5. Event and integration touchpoints (ForgeLedger alignment)

Use the **FID template** phases as the authoritative checklist where ForgeLedger is in scope:

- **Phase 1 (FID):** discovery & requirements → maps to MID Phase 0–1.
- **Phase 2 (FID):** architecture & event mapping → maps hook points to ledger event types (`concord.admission_decision`, `forgegate.policy_evaluation`, `warden.llm_call_metadata`, `agent.tool_call`, HITL events, etc.—exact names per your Ledger release).
- **Phase 3 (FID):** redaction, tenancy, keys.
- **Phase 4 (FID):** verification and export—including **claim boundary** language on evidence bundles.

ForgeRoot-wide, treat **Ledger emission as synchronous gate where policy demands it** (e.g., forensic visibility before intent finalization)—configure per posture in the questionnaire.

---

## 6. Deliverables (what “integrated” means)

Minimum package for downstream AI devs:

1. **Signed integration profile** (from questionnaire).
2. **Architecture diagram** of your harness annotated with ForgeRoot layers (even if stubbed).
3. **FID** or equivalent mapping document when ForgeLedger is used.
4. **Test reports** aligned to phased exit criteria (revocation, discovery kernel, sterile runtime, comprehension / dark-code, evidence export).

---

## 7. Governance doctrines (non-negotiable reminders)

These come directly from the whitepaper; localized shortcuts must not silently violate them:

- **Governance is decoupled from cognition.** Policy and admission are deterministic software boundaries.
- **Discovery is governed, not flat.**
- **Execution is sterile by default.**
- **Structural change is evidence-bound.**
- **Critical decisions must be replayable and auditable.**

---

## 8. Next documents to open

| Document | Use when |
|---------|----------|
| `forge_root_ai_dev_questionnaire.md` | Before writing integration code; drives cherry-picking and custom paths |
| `ResponsefromSAMsDev/forgeledger_integration_template.md` | Building the FID and event contracts |
| `ForgeLedger/third_party_integration_questionnaire.md` | Deep Ledger-only discovery complement |
| `forge_root_whitepaper_draft.md` | Architecture rationale, milestones, Addenda A/B |

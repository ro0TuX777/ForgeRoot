# ForgeGate: Deterministic Intent Governance

## Executive Summary

Artificial Intelligence agents can be brilliant at proposing actions and analyzing data, but they struggle with unbending consistency when evaluating risk. Organizations deploying multi-agent systems need an immovable enforcement point that can evaluate a proposed action against current environmental signals and definitively determine: *is this allowed, modified, escalated, or denied—and exactly why?*

**ForgeGate** is that deterministic action-governance gate. It acts as the final policy enforcement plane, intercepting proposed actions immediately before execution. By completely decoupling the decision process from hallucination-prone Large Language Models (LLMs), ForgeGate ensures that security boundaries, budgets, and compliance rules are enforced mathematically, producing a cryptographically verifiable `DecisionRecord`.

---

## The Problem Space

In standard agentic frameworks, the orchestrating LLM serves both as the actor (generating the tool call) and the judge (deciding if the tool call is safe based on the system prompt). This creates severe structural risks:
1. **Prompt Drift & Hallucination:** "System prompts" are highly malleable. An LLM instructed never to delete a production database might still do so if convinced the database is corrupt or a staging environment.
2. **Missing Determinism:** The same input might result in two different decisions depending on the temperature setting, model variant, or context window saturation.
3. **No Auditability:** When an LLM decides an action is safe, it rarely leaves a structured, actionable audit trail explaining the precise compliance rules it followed to reach that conclusion.

Enterprise agents fail most dangerously when they succeed at a proxy metric (e.g., speed of closing a ticket) while simultaneously degrading risk posture and operational safety.

---

## The ForgeGate Solution

ForgeGate solves these challenges by taking the final "decision" out of the LLM's hands. The LLM simply *proposes* an action, and ForgeGate deterministically evaluates it. 

The universal ForgeGate equation is:
**`ProposedAction + Signals (+ optional BudgetSnapshot) → DecisionRecord`**

### What ForgeGate is NOT
To understand ForgeGate, it is critical to understand its scoping boundaries:
- It is **not** an LLM policy decider. LLMs propose; ForgeGate decides deterministically.
- It is **not** a full agent orchestrator. It sits between the orchestrator and the execution environment.
- It is **not** a retrieval or context stack.

---

## The Evaluation Pipeline

When ForgeGate receives an intent specification (`ProposedAction` + `Signals`), it evaluates the request through a strict, deterministic sequence:

1. **Constraints (Deny / Escalate):** Hard limits. *(e.g., "If environment == 'production' and action == 'drop_table', DENY.")*
2. **Boundaries (Autonomy Caps → Escalate):** Limits on autonomy scope. *(e.g., "If the ticket affects PII data, require human approval: ESCALATE.")*
3. **Budgets (Exhausted → Deny / Escalate):** Resource and financial tracking. *(e.g., "If this action pushes the session over the compute budget, ESCALATE.")*
4. **Tradeoffs (Path Selection):** Configuration-driven pathing based on signals. *(e.g., Choose an active rule branch and record the branch ID.)*
5. **Shaping (ALLOW_WITH_MODS):** Precise mutation of the payload. *(e.g., "If TrustTier < T2, strip PII fields from webhook ingest events. ALLOW.")*

The final output is a `DecisionRecord` containing the explicit verdict and arrays of the specific rule IDs that were triggered.

---

## Canonical Hashing & Replay Safety

To guarantee an ironclad audit trail, ForgeGate embraces strict canonical hashing for every evaluation.
- **`input_hash`:** The SHA-256 hash of the canonically serialized `ProposedAction` and `Signals`.
- **`decision_id`:** The SHA-256 hash combining the intent version and the `input_hash`.

Because ForgeGate is deterministic, identical inputs will always produce the identical `decision_id` and output. This ensures total **replay safety**. Security teams can replay historical intent snapshots through updated gate rules to securely backtest policy changes without ever touching live infrastructure.

---

## Business Value

- **Mathematical Security:** Eradicates Prompt Injection risks at the capability boundary. Even if an LLM is perfectly hijacked by a malicious prompt, ForgeGate will deterministically evaluate and block the resulting bad actions.
- **Policy as Code:** Instead of writing complex, fuzzy guidelines in system prompts ("try to avoid doing X"), policies are hardcoded into clear, isolated rule constraints.
- **Traceable Auditing:** Every decision—whether it's an outright denial or an authorized shaping mutation—generates a hashed, immutable ledger entry. This makes cross-agency, military, and financial grade deployments provably compliant.

By treating governance as an independent, deterministic software layer rather than a language problem, ForgeGate is the critical safety valve that enables true agentic autonomy at scale.

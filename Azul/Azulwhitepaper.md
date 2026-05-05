# Azul: Agentic Change Verification System

## Executive Summary

As AI agents transition from read-only assistants to autonomous contributors, organizations face a critical bottleneck: reviewing their work. If an agent submits a 50-file refactor, a human engineer must spend hours validating its logical safety, defeating the speed benefits of AI.

**Azul** is the first comprehensive application built on top of the Forge framework ecosystem. It is an agentic change verification system that answers one definitive question before a change takes effect: *"Is this change safe?"* By serving as the ultimate CI/CD orchestrator for AI-proposed modifications, Azul replaces manual review with governed, deterministic behavioral verification, culminating in a cryptographic evidence trail.

---

## The Problem Space

Agentic software development introduces unique risks:
1. **The Evaluation Bottleneck:** AI can write code 100x faster than humans can review it. If humans must manually verify every pull request an agent generates, development velocity flatlines.
2. **Hidden Behavioral Shifts:** Agents may refactor a service to pass static tests, but inadvertently break subtle downstream operational behaviors or security bounds.
3. **Training Data Starvation:** It is computationally expensive to generate high-quality, verified training pairs to teach agents how to improve their workflows.

Organizations need a system that can reliably, automatically, and safely evaluate AI output in isolation before it ever touches staging or production.

---

## The Azul Solution

Azul is a long-running daemon that ingests proposed changes—whether they are GitHub Pull Requests, agent-proposed refactors, operational runbook updates, or security dependency patches. It packages these proposals into **Azul Tickets** and drives them through the entire ForgeRoot ecosystem.

Instead of duplicating the efforts of other systems, Azul acts as the supreme orchestrator over the Forge stack:
- **ForgeScaffold:** Maps the structural blast radius of the proposed change.
- **ForgeHarbor:** Provisions a secure, isolated "warm-pool" environment for testing.
- **ForgeAtlas:** Discovers which tools are available for the verification pipeline.
- **ForgeWorks & DAWN:** Executes the shadow pipeline to behaviorally test the change.
- **ForgeGate:** Applies deterministic rules to evaluate the test results (the `ReviewBundle`) against organizational policy.
- **CONCORD:** Ensures the entire verification was performed with governed trust boundaries.

---

## The Ticket Lifecycle

Every proposed change runs through a strict state machine, ensuring no verification phase is skipped:

1. **SUBMITTED:** A CI webhook, CLI trigger, or agent submits a change payload.
2. **ANALYZING:** Azul calls ForgeScaffold to map exactly which files, services, and downstream dependencies this change touches.
3. **PROVISIONING:** Azul requests a sterile, isolated container from ForgeHarbor.
4. **EVALUATING:** The change is dropped into the sterile container and executed via ForgeWorks to monitor its actual behavior against a "golden" oracle.
5. **COMPREHENSION GATE (Dark Code Layer 3):** To prevent "Dark Code" lacking human explainability, the proposing agent must emit a structured explanation of state management, architectural decisions, and dependency rationale. This generates a `ComprehensionReview`.
6. **GATING:** The results of the shadow run (`ReviewBundle`) and the `ComprehensionReview` are evaluated by ForgeGate policies (e.g., *Did coverage drop? Does the code contain undocumented state?*). If it tests perfectly but lacks comprehension, Azul issues a `WARN_DARK_CODE`.
7. **VERDICT (Completed / Warned / Rejected):** The ticket reaches a terminal state. Pass/Warn outcomes allow the change to be safely merged. 

---

## XP & Training Distillation

Azul is not just a bouncer; it is a trainer. When an intent or refactor passes through Azul's gates with a high verification score, Azul awards **XP** (Experience Points) mapping to the difficulty of the change.

More importantly, changes that successfully navigate the verification pipeline are automatically curated and emitted as **Verified Training Pairs**. This creates a localized, high-fidelity data loop: the outputs of successful agents are seamlessly converted into high-quality fine-tuning data, organically continuously improving the agent models without human data-curation labor.

---

## Business Value

- **Unblocks Agentic Velocity:** Replaces the human PR-review bottleneck with an automated, cryptographically secure behavioral evaluation system.
- **Zero-Trust CI/CD:** Treats every proposed change—whether written by an external vendor, an LLM, or an internal developer—with the exact same rigorous, containerized verification.
- **Self-Improving Ecosystem:** Solves the data-curation problem by automatically harvesting successful, verified agent runs into distillation pipelines to train smarter future agents.

Azul is the final layer that transforms agentic potential into enterprise-ready, production-safe reality.

# Forge Frameworks Ecosystem Overview

This document provides a high-level context for each of the core frameworks and services within the ForgeRoot ecosystem. It is intended for third-party agents and developers to quickly read, assess the utility of a particular framework, and determine its purpose before diving into detailed specifications.

## ForgeRoot
ForgeRoot serves as the overarching master repository and umbrella ecosystem for the multi-framework agentic engineering system. It acts as the core architectural implementation of the **Dark Code Framework**. Rather than asking "Did a human write this?", the ecosystem operates on the principle "Can a human comprehend this?". It absorbs the 3 Layers of Dark Code logic by integrating intent admission (Layer 1: Spec-driven context), deterministic codebase mapping (Layer 2: Self-describing Systems), and exhaustive verification (Layer 3: Comprehension Gate). By doing so, ForgeRoot ensures that AI-driven software development remains secure, deterministic, explicitly documented, and strictly audited.

## Azul
**Agentic Change Verification System**: Azul operates as the top-level application layer that orchestrates the entire Forge stack to answer a single critical question: *"Is this proposed code change safe?"* Before any change (such as a pull request, an agent-proposed refactor, or a security patch) takes effect, Azul runs the change through a governed behavioral evaluation in an isolated environment. It returns a structured verdict (pass, reject, or warn) complete with an exhaustive and human-readable evidence trail.

## CONCORD
**Governance Specification & Admission Pipeline**: CONCORD defines the foundational governance rules determining which agents are authorized to take specific actions. By mapping `AgentClasses` to explicitly allowed `CapabilitySets`, `TrustTiers`, and budgets, CONCORD acts as the ecosystem's admission gate. Every agent request forms an Intent that must pass through CONCORD's rigorous assessment pipeline before it is even considered for execution.

## ForgeAtlas
**ActionDiscovery Service**: Acting as the system's queryable "tool shed" or atlas, ForgeAtlas enables agents to discover available actions dynamically instead of needing hundreds of system actions loaded into their context window. It securely filters the available `ActionContracts` based on the querying agent's capabilities and trust tier, utilizing local semantic search to rank discovery results by relevance to the agent's natural-language task description.

## ForgeGate
**Deterministic Intent Governance**: ForgeGate provides a deterministic enforcement point that decides whether an admitted intent is permitted to execute. Rather than relying on potentially hallucinating LLMs for security decisions, ForgeGate evaluates the `ProposedAction` and system state `Signals` against hardcoded constraints, boundaries, and budgets limiters. It output an auditable `DecisionRecord` detailing if an action was allowed, denied, or allowed with modifications.

## ForgeHarbor
**Warm-Pool ExecutionEnvironment Orchestrator**: To prevent slow cold starts for executing isolated agent tasks, ForgeHarbor provisions and manages a "warm pool" of ready-to-run Docker containers. When an agent session requires execution, ForgeHarbor assigns an isolated, secure environment running the DAWN execution engine instantly. Once the session finishes, ForgeHarbor seamlessly drains, recycles, and replenishes the environment pool in the background.

## ForgeScaffold
**Blueprint Generation & Change Management**: ForgeScaffold provides a unified blueprint structure for mapping codebases deterministically—regardless of whether they are user-facing monoliths, service meshes, or AI agent applications. It catalogs system units, maps data flow boundaries, enforces centralized observability schemas, and establishes strict "Definition of Done" success contracts, ensuring that structural codebase refactors can be applied without untracked regressions.

# ForgeAtlas: Semantic Capability Discovery

## Executive Summary

As enterprise AI agents scale their capabilities, they quickly outgrow simple, hardcoded system prompts. An agent equipped with hundreds or thousands of system actions cannot load all of them into its context window, nor can it navigate rigid, hierarchical documentation to find the right tool for a dynamic problem. 

**ForgeAtlas** serves as the deterministic "ActionDiscovery Service" or "Capability Shed" for the ForgeRoot ecosystem. It exposes a naturally queryable, highly performant directory of actions that agents can interact with. More critically, ForgeAtlas is strictly governed: an agent will never discover actions that it lacks the trust tier or capability scope to execute. 

---

## The Problem Space

Managing agent capabilities in complex multi-tenant environments introduces several crippling issues:
1. **Context Window Exhaustion:** Passing a full catalog of API contracts, schemas, and usage examples into every LLM request destroys context lengths and severely inflates inference costs.
2. **Brittle Tool Matching:** Standard architectures force agents to exact-match tool names. If an agent doesn't know the exact string ID for "emergency_restart", it fails. Meaningful, localized capability resolution is missing.
3. **Implicit Privilege Leakage:** In flat discovery models, a low-trust agent might discover a high-trust administrative action. It may be denied upon execution, but exposing the schema and existence of secure capabilities violates zero-trust principles.

---

## The ForgeAtlas Solution

ForgeAtlas solves these problems by providing an advisory, queryable interface strictly integrated with CONCORD governance. When an agent has a task, it queries ForgeAtlas in natural language describing what it is trying to achieve. ForgeAtlas scores all available actions, filters out those the agent is unauthorized to use, and returns a lightweight payload of highly relevant tools.

### Core Architecture

ForgeAtlas wraps execution discovery into three decoupled layers:

#### 1. Catalog Persistence Layer
The service manages an immutable, human-editable directory of YAML manifest files representing `ActionContracts`. On startup, it deterministically validates these manifests and loads them into an in-memory, version-controlled registry. Because the catalog is content-addressed, agents and applications can accurately cache available endpoints.

#### 2. Semantic Search Layer
When the service receives a natural language intent (e.g., *"I need to restart the staging database"*), it embeds the query using a fast, localized sentence-transformer model. It runs cosine similarity ranking against all registered action descriptions, translating human task descriptions directly into executable tool endpoints.

#### 3. Service Wrapper Layer
ForgeAtlas operates as a fully governed, Docker-portable service block. Rather than standing up heavy gRPC or HTTP overhead, it follows lightweight service patterns with strict `_ok/_error` envelopes, delivering high-performance, predictable responses directly to the orchestrating runtime.

---

## The Trust Invariant: Governed Discovery

The single most important principle of ForgeAtlas is its intersection with the CONCORD specification: **An agent MUST NOT discover actions it cannot admit.**

Before returning the semantically ranked tools, ForgeAtlas cross-references the querying agent's `CapabilitySet` and `TrustTier`. 
- If an action requires a `T3` military-grade trust tier, and the querying agent is `T1` open-data tier, that action is silently redacted from the search results.
- This creates true multi-tenant capability masking. Identical semantic queries from different agents will return entirely different operational capabilities based strictly on verified identity parameters.

Furthermore, ForgeAtlas respects context limits natively: it defaults to returning lightweight action summaries and only transmits heavy JSON validation schemas precisely when the agent specifically requests them.

---

## Business Value

- **Infinite Action Scaling:** Organizations can deploy thousands of custom actions, webhook handlers, and microservice wrappers without crashing agent context windows.
- **Zero-Trust Tooling:** "Invisible" capabilities ensure highly sensitive actions remain undiscoverable to compromised, external, or low-trust autonomous agents.
- **Autonomous Recovery:** Because ForgeAtlas understands semantic proximity, when an agent fails an execution track, it can dynamically query ForgeAtlas for alternative tooling routes, enabling true self-healing automation.

ForgeAtlas fundamentally transforms agent tooling from a hardcoded list into a dynamic, zero-trust App Store, governed by cryptographic rules.

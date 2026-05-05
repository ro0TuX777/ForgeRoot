# CONCORD Framework — Integration Lessons Learned
**Scope:** Universal guidance for agent-to-governed-service integrations  
**Derived from:** A completed end-to-end integration between an autonomous agent team and a governed forensic analysis service  
**Date:** 2026-04-18

---

## Overview

The following recommendations address friction points that emerged during a full integration lifecycle — from initial wiring through environment configuration, SDK path resolution, action contract negotiation, and file ingestion. Each recommendation is framed as a framework-level capability or convention, not tied to any specific implementation.

---

## 1. SDK Client Contract: Receipt IDs Must Be First-Class

**Problem encountered:**  
The governed SDK provided typed action wrappers (e.g. `client.analyze_pcap(...)`) that internally called `submit()` but discarded the `receipt_id` from the CONCORD response. Integrators who used the typed wrappers had no way to capture CONCORD audit receipts without bypassing the SDK entirely and calling `submit()` directly.

**Recommendation:**  
Every typed SDK wrapper that wraps a `submit()` call must return the full CONCORD response envelope, including `receipt_id`, as a first-class field. Typed wrappers are convenience layers — they must not silently drop governance artifacts that the caller has a legitimate right to retain.

**Minimum contract:**
```
TypedActionResult:
  success: bool
  receipt_id: str          ← always present, even on failure
  result: dict
  cost_deducted: int
  error: str | None
```

---

## 2. Health Check Surface: Distinguish Failure Modes

**Problem encountered:**  
The adapter's health check returned a single boolean (`healthy: true/false`). When the SDK could not be imported (wrong path, missing module), the health check caught the `ImportError` and returned `healthy=false` — indistinguishable from a network connectivity failure. This caused the error message to report "service not reachable" when the actual problem was "SDK not installed in this runtime environment."

**Recommendation:**  
The `deploy/status` health endpoint and the client-side `is_healthy()` method should distinguish at least three failure classes:

| Class | Meaning |
|---|---|
| `sdk_unavailable` | Client library not importable in current runtime |
| `service_unreachable` | Network/connection failure to the governed service |
| `pipeline_not_ready` | Service reachable but pipeline not in ready state |

Agent adapters should surface the failure class in structured error output so debugging does not require log inspection.

---

## 3. Action Input Schema: Declare File Handling Semantics Explicitly

**Problem encountered:**  
A file-accepting governed action included a `filename` parameter in its input schema. The integrating agent interpreted this as a host filesystem path. The governed service interpreted it as a basename within its own managed storage. Neither interpretation was declared in the schema — the mismatch was only discovered at runtime when validation failed.

**Recommendation:**  
Any CONCORD action that accepts file references must declare its file handling semantics explicitly in the action's `inputSchema`:

```json
{
  "filename": {
    "type": "string",
    "description": "Basename of the file as it will appear in managed storage. Not a host path.",
    "example": "capture.pcap"
  },
  "source_path": {
    "type": "string",
    "description": "Optional. Absolute path within the configured ingest root. The service will materialize the file into managed storage. If omitted, the file must already exist in managed storage.",
    "example": "/ingest/captures/capture.pcap"
  }
}
```

The key principle: **a `filename` parameter is a storage key, not a filesystem path. If filesystem path input is supported, it must be a named, documented parameter with declared constraints.**

---

## 4. Ingest Root: Define and Advertise It from Day One

**Problem encountered:**  
The governed service had no configured ingest root when integration began. File materialization was not part of the initial governed action contract. The concept was only introduced after the integrating agent discovered at runtime that the service could not access external file paths. This required both sides to negotiate a new contract mid-integration, add a new parameter, configure a bind mount, and rebuild the service.

**Recommendation:**  
Any CONCORD-governed service that processes files should define its ingest root as a required configuration item from the initial deployment specification. It should be:

1. Documented in the action's capability advertisement
2. Advertised in the `deploy/status` response:
   ```json
   {
     "status": "ready",
     "ingest_root": "/ingest",
     "ingest_root_configured": true
   }
   ```
3. Validated at service startup — if file-accepting actions are registered but no ingest root is configured, the pipeline should start in a degraded state with a clear diagnostic

**The ingest root is a governance boundary, not an implementation detail.** Agents operating under CONCORD need to know where they may and may not direct files.

---

## 5. Executor Validation: Schema-Declared Fields Must Be Runtime-Enforced

**Problem encountered:**  
An executor's database insert for a file record failed at runtime with a `NOT NULL` constraint violation on a timestamp field. The field was required by the database schema but was not being populated by the executor. This was discovered through a live CONCORD execution failure, not at schema definition time.

**Recommendation:**  
CONCORD executor authors should treat the governed action's output schema as a testable contract, not documentation. Required fields in the output (or in internal data models) should be validated by unit or integration tests at the executor boundary before the action is registered in the CONCORD action registry.

A governed action that fails its own output contract is a governance violation — it produces an execution failure inside the admission pipeline and forces the agent to treat a coding bug as an availability event.

**Minimum practice:** Every executor that writes to persistent storage should have at least one integration test that exercises the full write path and asserts no `None` values reach non-nullable columns.

---

## 6. Capability Advertisement: Publish Required Environment Configuration

**Problem encountered:**  
The integrating adapter required multiple environment variables to be correctly set across multiple runtime environments (containerized services, SDK path injection, URL configuration, feature flags, trust tiers). These were discovered incrementally — one missing variable per failed run — because there was no single source of truth for what the integration required.

**Recommendation:**  
The CONCORD `/capabilities` or `deploy/status` endpoint should include a `required_configuration` block listing the environment variables or configuration keys the governed service depends on:

```json
{
  "status": "ready",
  "required_configuration": {
    "GOVERNED_SERVICE_URL": { "required": true, "description": "Base URL of the governed service" },
    "INGEST_ROOT": { "required": true, "description": "Filesystem root for file ingestion" },
    "AGENT_CLASS": { "required": false, "default": "default_agent", "description": "CONCORD session agent class" },
    "TRUST_TIER": { "required": false, "default": 1 }
  }
}
```

This allows the agent adapter to perform a configuration completeness check before submitting any actions, rather than discovering missing configuration through runtime failures.

---

## 7. Feature Flags: Return Structured Responses, Not Silent Skips

**Problem encountered:**  
When the integration feature flag was disabled, the agent returned a `SKIPPED` verdict and the ticket completed normally with no indication to the operator that analysis had not run. From the operator's perspective, the ticket succeeded — but no forensic analysis was performed.

**Recommendation:**  
A CONCORD-governed action that is gated behind a feature flag should return a structured, machine-readable response distinguishing three states:

| State | Meaning |
|---|---|
| `DISABLED` | Feature flag explicitly off — analysis intentionally skipped |
| `UNAVAILABLE` | Feature enabled but service unreachable — fail-open or fail-closed per policy |
| `COMPLETED` | Analysis ran and produced a result |

`DISABLED` and `UNAVAILABLE` should be treated as different operational states. Operators and downstream consumers should be able to filter for tickets where analysis was not performed, rather than having `SKIPPED` silently blend in with `COMPLETED`.

---

## 8. Cross-Environment SDK Path: Validate at Adapter Initialization

**Problem encountered:**  
The SDK path was injected into the Python runtime path using a host-side filesystem path (Windows format). When the adapter ran inside a Linux container, the path did not exist, the import silently failed, and the health check returned `service_unreachable` — pointing at a network problem that did not exist.

**Recommendation:**  
Any adapter that injects a filesystem path to locate an SDK should validate path existence at initialization time and emit a specific structured error if the path is not found:

```
AdapterInitializationError:
  code: SDK_PATH_NOT_FOUND
  sdk_path: "/injected/path"
  message: "SDK path does not exist in current runtime environment. 
            Set GOVERNED_SDK_PATH to a path accessible from this process."
```

This is distinct from a health check failure. Initialization errors should not be surfaced as connectivity errors. Path injection across OS or container boundaries is a known fragile pattern — explicit validation at init time surfaces it immediately.

---

## 9. Governed Action Contracts: Separate Display Name from Storage Key

**Problem encountered:**  
A single `filename` field was used both as a human-readable display name and as a storage addressing key. Operators naturally treated it as a filesystem path because that is how filenames are commonly understood in operational tooling. The governed service treated it as a basename within its own storage namespace. The field name did not communicate which interpretation was correct.

**Recommendation:**  
CONCORD action schemas should use distinct parameter names when a value serves different roles:

| Role | Recommended Parameter Name |
|---|---|
| Human-readable label | `display_name` or `label` |
| Basename in managed storage | `filename` |
| External filesystem reference | `source_path` |
| URN/identifier in a governed namespace | `resource_id` |

Naming clarity at the schema level eliminates a class of runtime failures entirely. An agent that reads `source_path` in a schema description knows it is providing a filesystem reference. An agent that reads `filename` knows it is providing a storage basename. The schema should never require the agent to infer which role a parameter serves.

---

## 10. Container Networking: Governed Service URLs Must Use Service-Mesh Names

**Problem encountered:**  
The integrating agent's service defaulted its governed-service URL to `localhost:<port>`. When the agent ran inside a container, `localhost` resolved to the container itself, not the governed service container on the shared network. The governed service was reachable by its service mesh name but not by `localhost`.

**Recommendation:**  
CONCORD-governed service deployments should document and default to service-mesh-resolvable names for inter-container communication. The adapter's default URL should never be `localhost` in a containerized deployment context. The `deploy/status` endpoint should be used as the liveness check in container health configurations so that connectivity is validated using the same URL the adapter will use at runtime.

Additionally, container environment definitions for consuming services should explicitly set the governed service URL as a named environment variable using the mesh-resolvable hostname, not rely on default fallback values.

---

## Summary Table

| # | Lesson | Framework Layer |
|---|---|---|
| 1 | Receipt IDs must be first-class in typed SDK wrappers | SDK / Client |
| 2 | Health check must distinguish SDK unavailable vs service unreachable vs not ready | Client / Health |
| 3 | File-accepting actions must declare storage semantics in input schema | Action Schema |
| 4 | Ingest root must be defined, configured, and advertised from day one | Deployment / Capability |
| 5 | Executor output contracts must be integration-tested before registration | Executor / Testing |
| 6 | Required configuration must be published in capability advertisement | Capability Advertisement |
| 7 | Feature flag states must be machine-readable and distinct from each other | Agent / Flag Design |
| 8 | SDK path injection must be validated at adapter init, not at health check | Adapter / Init |
| 9 | Display name, storage key, and filesystem path must be separate parameters | Action Schema |
| 10 | Container networking requires service-mesh names, not localhost defaults | Deployment / Networking |

---

*Generated from a completed agent-to-governed-service integration lifecycle. All recommendations are framework-agnostic and apply to any CONCORD-governed service and agent pairing.*

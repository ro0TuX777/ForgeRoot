# CONCORD Integration Guide

**Status:** Normative Companion Document | **Version:** 0.5.1 | **Date:** April 2026  
**Audience:** Any AI agent or development team tasked with wiring a host application to accept CONCORD governance  
**Prerequisite reading:** All v0.5 spec documents (Admission Pipeline, Error Catalog, Runtime Endpoints, ReviewBundle & OperationContext)  
**Optional reading:** [MCP Adapter Profile](CONCORD_v0.5_MCP_Adapter_Profile.md) — for exposing CONCORD capabilities via the Model Context Protocol  
**Amended by:** SAM integration lessons (v0.5.1) — parameter naming conventions, executor registration gate  

---

## 1. Purpose

This guide provides normative instructions for integrating CONCORD governance into an existing application. It was derived from the first real-world CONCORD integration and generalized to be **application-agnostic** — it applies to any web application, legacy system, or service regardless of technology stack, framework, or domain.

This is not a tutorial. It is a **contract obligations document** that specifies what the integration must produce and the mistakes it must avoid.

---

## 2. Mental Model

### 2.1 You Are Building a Governed Execution Pipeline

The most critical mental model: you are building a **governed execution pipeline** that sits between agent consumers and the host application's existing business logic.

You are NOT:
- "Adding CONCORD endpoints to the app"
- Modifying existing routes, templates, or frontend logic
- Building a thin API wrapper over existing functionality

You ARE:
- Building a new entry surface that receives structured intent requests from agents
- Running those requests through the CONCORD Admission Pipeline (see Admission Pipeline Specification)
- Delegating to the host application's business logic layer
- Normalizing output into structured, schema-conformant responses
- Returning governed receipts

### 2.2 Two Surfaces, One Logic Layer

The host application continues to serve human users through its existing routes. The CONCORD integration adds a **parallel entry surface** for agent consumers. Both surfaces share the same business logic layer. Everything above that layer — routing, authentication, response formatting — is separate.

```
┌────────────────────────────────────────────────────┐
│                  Host Application                   │
│                                                     │
│  ┌──────────────────┐    ┌───────────────────────┐ │
│  │  Human Surface    │    │  Agent Surface         │ │
│  │  ─────────────    │    │  ─────────────────     │ │
│  │  Existing routes  │    │  CONCORD Pipeline      │ │
│  │  HTML templates   │    │  JSON request/response │ │
│  │  Session cookies  │    │  Session tokens        │ │
│  │  Form validation  │    │  Schema validation     │ │
│  │  Error pages      │    │  Error catalog         │ │
│  └────────┬─────────┘    └──────────┬────────────┘ │
│           │                         │               │
│           │    ┌────────────────┐   │               │
│           └───→│ Business Logic │←──┘               │
│                │     Layer      │                    │
│                └────────────────┘                    │
└────────────────────────────────────────────────────┘
```

**Do NOT modify the human surface.** The legacy routes, templates, and frontend logic are not your concern. They continue working exactly as they did before the integration.

---

## 3. Integration Sequence

Follow these steps in order. Each step has dependencies on previous steps.

### 3.1 Step 1 — Capability Audit

Before writing any code, audit the host application and identify every discrete capability it offers. Each capability becomes an **ActionContract**.

For each capability, document:

| Field | What to Determine |
|---|---|
| **Name** | Use `family.verb` convention (e.g., `scan.static_analysis`, `report.export_pdf`, `data.import_csv`) |
| **Action family** | Classify: `read`, `plan`, `mutate`, `approve`, `deploy`, `compensate` |
| **Minimum trust tier** | What level of agent autonomy is appropriate? T0 (sandbox) through T4 (unattended)? |
| **Guards** | What preconditions must be true? (service healthy, resource accessible, config valid, quota available) |
| **`input_schema`** | What parameters does the capability need? Express as JSON Schema (draft 2020-12). Be explicit about types, required fields, and constraints. |
| **`output_schema`** | What structured data should the agent receive? This is NOT what the legacy code returns today. This is what the agent NEEDS for decision-making. |
| **Cost** | Assign a budget cost (in risk-weighted units) so the BudgetGate can enforce limits |
| **Idempotency** | Can this action be safely retried? Is the operation naturally idempotent, or does it need idempotency key enforcement? |

**Get this registry right before writing any pipeline code.**

### 3.1.1 Parameter Naming Conventions (v0.5.1 — Normative)

When an action schema includes parameters that reference files, resources, or identifiers, the parameter name MUST communicate the parameter's role unambiguously. Overloaded names (e.g., a single `filename` field used as both a display label and a storage key) create integration failures. This was the root cause of the longest debugging loop in the SAM integration.

**Normative naming conventions for file and resource parameters:**

| Role | Parameter Name | Semantics |
|---|---|---|
| Human-readable label | `display_name` | For UI/logging only. No addressing or storage role. |
| Basename in managed storage | `filename` | Storage key within the service's namespace. NEVER a filesystem path. |
| External filesystem reference | `source_path` | Absolute path within the ingest root. Container-aware. |
| Resource identifier (governed) | `resource_id` | URN or opaque ID in a governed namespace. |
| Output file destination | `output_path` | Where result artifacts should be written. |

**File-handling storage model declaration:**

Any action that accepts file references MUST declare its storage model in the `input_schema` description. The two models are:

| Model | Meaning |
|---|---|
| `managed_storage` | Service stores the file internally. `filename` is a key in the service's namespace. |
| `external_ingest` | Service reads from an ingest root. `source_path` is a path within that root. |

If an action supports BOTH models, BOTH parameters MUST be present with conditional logic documented.

**Example input_schema for a file-accepting action:**

```json
{
  "filename": {
    "type": "string",
    "description": "Basename of the file in managed storage. Not a filesystem path.",
    "example": "capture.pcap"
  },
  "source_path": {
    "type": "string",
    "description": "Absolute path within the ingest root. Service will materialize into managed storage. Required if file is not already in managed storage.",
    "example": "/ingest/captures/capture.pcap"
  },
  "display_name": {
    "type": "string",
    "description": "Human-readable label for reports and logs. No addressing role.",
    "example": "Network capture from incident #4521"
  }
}
```

**Why normative, not advisory:** The SAM integration's longest debugging session was caused by a single `filename` parameter that the calling agent interpreted as a host filesystem path while the governed service interpreted it as a managed storage basename. Neither interpretation was declared in the schema. Making these naming conventions normative eliminates this class of ambiguity by construction.

### 3.3 Step 3 — Build the Executor Registry

For each ActionContract, implement an executor callable:

```
Executor callable signature:
  (parameters: dict, session: Session, action_contract: ActionContract) → ExecutionResult

ExecutionResult:
  success:        bool
  result_summary: object?    # raw output from business logic
  error_code:     string?    # if failed
  error_detail:   string?    # human-readable error
```

**Important:** Executors delegate to the host application's business logic layer. They do NOT implement the business logic themselves.

### 3.4 Step 4 — Build the Normalizer Registry

For each ActionContract with an `output_schema`, implement a normalizer callable:

```
Normalizer callable signature:
  (raw_result: object, action_contract: ActionContract) → NormalizationResult

NormalizationResult:
  success:        bool
  normalized:     object?    # schema-conformant output
  warnings:       array      # non-fatal issues
  error_detail:   string?    # if failed
```

Normalizers transform raw business logic output into structured, schema-conformant responses that agents can reason over.

### 3.5 Step 5 — Implement the Admission Pipeline

Implement the full CONCORD Admission Pipeline (see Admission Pipeline Specification):

1. Session resolution
2. Action resolution
3. Trust gate
4. Budget gate
5. Input validation (JSON Schema Draft 2020-12)
6. Guard evaluation
7. Idempotency check
8. Intent creation
9. Execution delegation
10. Output normalization
11. Receipt minting (with output validation)

### 3.6 Step 6 — Wire the Runtime Endpoints

Implement the required runtime endpoints (see Runtime Endpoint Contracts):

- `/intent/submit` — admission pipeline entry
- `/actions` — list ActionContracts
- `/operation-context/{action_name}` — planning surface
- `/budget/status` — budget introspection
- `/budget/estimate` — workflow feasibility check
- `/session/refresh` — session extension
- `/receipt/{receipt_id}` — receipt retrieval

### 3.7 Step 7 — Add Receipt Validation

Receipts must validate output against the ActionContract's `output_schema` using JSON Schema Draft 2020-12. Validation errors are recorded in the receipt but do not fail the operation unless critical.

### 3.8 Step 8 — Test and Validate

Run the integration validation checklist:

- All endpoints return correct schemas
- Error codes match the Error Catalog
- Guards execute with parameter-dependent logic
- Budget deduction and estimation work
- Session lifecycle (creation, refresh, expiration)
- Idempotency prevents duplicate execution
- JSON Schema validation catches invalid inputs/outputs
- Receipts are retrievable and validated

Register all guards in a Guard Registry (a map of guard name → callable). Every guard declared on any ActionContract MUST have a corresponding registry entry.

**Startup validation:** When the pipeline initializes, cross-reference every declared guard name against the registry. Missing entries are a deploy-time failure, not a runtime surprise.

**Common guard patterns:**

| Guard Name Pattern | What It Checks |
|---|---|
| `service_healthy` | External dependency responds to health check |
| `resource_accessible` | Target file/database/API is reachable |
| `config_valid` | Required configuration values are present and well-formed |
| `token_configured` | Required API tokens or credentials are set |
| `quota_available` | External service quota has not been exhausted |
| `resource_not_locked` | No conflicting lease exists on the target resource |

### 3.3 Step 3 — Build the Executor

The executor bridges CONCORD intents to host application function calls. It is a **translation layer** with three responsibilities:

#### 3.3.1 Parameter Translation

Map the ActionContract's `input_schema` field names to the arguments the host application's function expects. Names may differ. Formats may need conversion.

Example:
```
ActionContract input_schema:
  { "target_directory": "string", "max_depth": "integer" }

Host function signature:
  run_scan(path: str, depth: int = 10)

Parameter translation:
  path  ← parameters["target_directory"]
  depth ← parameters["max_depth"]
```

#### 3.3.2 Exception Classification

Catch **every** exception the host application can throw and map it to a CONCORD error catalog entry. Build an exception mapping table (see Error Catalog Amendments, §4).

**The most common mistake is `return host_function(**params)`.** This produces raw, unclassified exceptions and unpredictable output. The executor is where you earn the governance contract.

**Default handler:** Unmatched exceptions MUST map to `EXECUTION_FAILED` with `agent_should: report`. No raw traceback may escape the executor boundary.

#### 3.3.3 Result Packaging

Return the host function's output as `raw_output` in the ExecutionResult. The executor does NOT normalize output — that is the OutputNormalization stage's responsibility. But the executor MUST ensure `raw_output` is serializable (no open file handles, database cursors, or framework-specific objects).

### 3.4 Step 4 — Build Output Normalizers

For each ActionContract that declares an `output_schema`, build a normalizer function:

```
Normalizer signature:
  (raw_output: any, action_contract: ActionContract) → NormalizationResult

NormalizationResult:
  normalized:  object    # output conforming to output_schema
  warnings:    array?    # fields that couldn't be mapped
  raw_ref:     string?   # optional reference to raw output
```

**This is the highest-value work in the entire integration.**

The host application was built for humans — its outputs are HTML pages, formatted strings, log files, downloadable reports, database result sets. The agent needs structured, parseable data with consistent field names and predictable shapes.

For each normalizer:
- Extract structured data from whatever the host function returns
- Map it to the `output_schema` fields
- Handle edge cases: empty results, partial failures, timeout results, error objects
- Include metadata the agent needs for decision-making (counts, severity levels, confidence scores, pass/fail status)
- MUST NOT throw exceptions — return a failed NormalizationResult with warnings instead

**Without normalizers, the agent receives results it cannot parse, and the entire integration is governance theater.**

### 3.5 Step 5 — Wire the Admission Pipeline

Implement the 11-stage admission pipeline as specified in the Admission Pipeline Specification. The pipeline is a separate entry surface — a new blueprint, router, or controller that owns the agent-facing API.

**Key implementation rules:**
- Stages MUST execute in the specified order
- Fail-fast: stop on first failure, return the corresponding error code
- All entry points (direct intent, dispatch, batch, webhook) share the same pipeline
- No convenience endpoints that skip stages
- Admission stages (①–⑧) must be side-effect-free
- Cost is deducted at ReceiptMinting (⑪), not at BudgetGate (④)

### 3.6 Step 6 — Wire the Planning Endpoints

Implement the planning-time endpoints alongside the admission pipeline:

- **OperationContext** (v0.3, extended in v0.5): returns action metadata, trust constraints, budget snapshot, guard pre-evaluation, and session constraints
- **Budget Status** (v0.5): returns remaining budget by category
- **Budget Estimate** (v0.5, optional): returns whether a planned workflow fits within budget
- **Session Refresh** (v0.5): extends session TTL without creating a new session

These endpoints are read-only (except Session Refresh, which is auditable) and do not flow through the admission pipeline.

### 3.7 Step 7 — Deterministic Port Assignment

**Owner:** Deployment Agent

Before building or starting containers, the Deployment Agent MUST assign host ports using a **deterministic, application-unique** algorithm. This eliminates port collisions with co-located applications without requiring a runtime port scan.

**Why not scan-and-remap?** Scanning finds conflicts reactively, after they happen. Deterministic assignment prevents them by construction — the same application always maps to the same port range, regardless of what else runs on the host. This makes deployments reproducible and manifests stable.

**Algorithm: Name-Derived Port Assignment**

```
Input:    application_name  — the CONCORD registration name (lowercase, e.g., "bluescrub")
Output:   base_port         — the starting host port for this application's services
Range:    [10000, 65000]    — avoids well-known ports (0–1023) and common dev ports (3000–9999)

Procedure:
  1. Compute weighted character hash:
     hash = sum( ord(c) × (i + 1) )   for each character c at position i in application_name

  2. Map into port range:
     base_port = 10000 + (hash mod 55000)

  3. Assign service ports sequentially:
     service_0_port = base_port + 0
     service_1_port = base_port + 1
     service_n_port = base_port + n

  4. Collision fallback (rare):
     If any assigned port is occupied on the host, increment that port by 100.
     Repeat until free. Log the remap to DEPLOYMENT_NOTES.md.
```

**Reference calculations:**

| Application | Hash Computation | Hash | Base Port |
|---|---|---|---|
| `bluescrub` | `98×1 + 108×2 + 117×3 + 101×4 + 115×5 + 99×6 + 114×7 + 117×8 + 98×9` | 4854 | **14854** |
| `mnemos` | `109×1 + 110×2 + 101×3 + 109×4 + 111×5 + 115×6` | 2313 | **12313** |
| `sam` | `115×1 + 97×2 + 109×3` | 636 | **10636** |

**Properties:**
- **Deterministic:** Same name always produces the same ports on any host
- **Position-sensitive:** Anagrams (e.g., `parts` vs `strap`) produce different hashes
- **Collision-resistant:** 55,000-port range with typical app names of 4–15 characters provides wide distribution
- **Reproducible:** Manifests are stable across redeployments — consuming agents don't need reconfiguration

**The Deployment Agent MUST update `docker-compose.yml`** (or equivalent) to use the computed ports for host-side bindings. Internal container ports remain unchanged.

```yaml
# Before (default ports — collision-prone):
ports:
  - "5000:5000"   # host-api
  - "8630:8630"   # analysis
  - "8620:8620"   # cyberscan

# After (deterministic ports for "bluescrub"):
ports:
  - "14854:5000"  # host-api    (base_port + 0)
  - "14855:8630"  # analysis    (base_port + 1)
  - "14856:8620"  # cyberscan   (base_port + 2)
```

### 3.8 Step 8 — `.dockerignore` Generation

**Owner:** Deployment Agent

If no `.dockerignore` exists in the build context directory, the Deployment Agent MUST generate one. Without it, `COPY . .` in Dockerfiles sends the entire project tree as build context — including `.git/`, test fixtures, and sibling service directories.

**Template `.dockerignore`:**

```
# Version control
.git
.gitignore

# Python artifacts
__pycache__
*.pyc
*.pyo
*.egg-info
.venv
venv

# Node artifacts
node_modules

# IDE and OS
.vscode
.idea
*.swp
.DS_Store
Thumbs.db

# Docker
docker-compose*.yml
Dockerfile*
.dockerignore

# Documentation and non-runtime files
*.md
LICENSE

# Test data
tests/
test_data/
fixtures/

# Service directories (each service builds its own context)
services/
```

The Deployment Agent SHOULD adapt this template to the host application's structure (e.g., add framework-specific exclusions). The goal is to reduce build context to only the files needed inside the container.

### 3.9 Step 9 — Build Validation

**Owner:** Deployment Agent

Before starting containers, run a full build and classify any failures:

```bash
docker compose build --no-cache 2>&1
```

If the build fails, the Deployment Agent MUST classify the error:

| Failure Class | Indicators | Agent Action |
|---|---|---|
| **Dependency resolution** | `pip install` / `npm install` failure, version conflict, package not found | Attempt fix: pin alternative version, remove abandoned package, resolve conflict. Log to `DEPLOYMENT_NOTES.md`. |
| **Network error** | Registry timeout, DNS failure, certificate error | Retry with backoff. If persistent, report `DEPLOY_BUILD_FAILED`. |
| **Dockerfile syntax** | Invalid instruction, bad `FROM` reference | Report `DEPLOY_BUILD_FAILED` — requires human/Integration Agent fix. |
| **Base image unavailable** | `manifest not found`, `pull access denied` | Check for image name typo, tag existence, or registry authentication. |

Build validation is **not optional**. A `docker compose up` on unbuilt or broken images produces cryptic runtime failures that are harder to diagnose than build-time errors.

### 3.10 Step 10 — Start & Health Probe

**Owner:** Deployment Agent

Start the application stack and validate that every service is healthy:

```bash
docker compose up -d
```

**Health probe sequence:**

```
For each service defined in docker-compose.yml:
  1. Wait for container status = "running" (timeout: 30s)
  2. If the service declares a healthcheck in compose → wait for healthy status (timeout: 120s)
  3. If no healthcheck → probe the service's HTTP health endpoint:
       GET http://localhost:{host_port}/health
       Expected: HTTP 200 with body containing {"status": "healthy"} or equivalent
       Timeout: 120s with 5s poll interval
  4. For database services → use protocol-specific readiness:
       PostgreSQL: pg_isready -h localhost -p {host_port}
       Redis: redis-cli -p {host_port} ping
       MongoDB: mongosh --port {host_port} --eval "db.adminCommand('ping')"
  5. On timeout or failure:
       - Capture: docker logs {container_name} --tail 50
       - Report: DEPLOY_HEALTH_TIMEOUT with container logs attached
       - Do NOT proceed to manifest generation
```

**All services must be healthy before proceeding.** A partial deployment (some services up, some down) produces intermittent failures that are worse than a clean "not deployed" state.

### 3.11 Step 11 — Platform-Specific Checks

**Owner:** Deployment Agent

Detect the host OS and apply platform-specific validations:

**Docker Desktop (Windows):**

| Check | Problem | Remediation |
|---|---|---|
| `network_mode: host` | Runs inside HyperV/WSL2 VM — ports not forwarded to Windows host | Switch to bridge networking with `cap_add: [NET_RAW, NET_ADMIN]` if raw socket access needed |
| Volume paths with backslashes | Docker expects forward slashes | Convert `C:\path\to\dir` → `/c/path/to/dir` or use relative paths |
| WSL2 integration | Docker may not be accessible from non-default WSL distros | Verify `docker info` succeeds from the execution context |
| File watching | inotify doesn't propagate across VM boundary | Use polling-based watchers for development volumes |

**Docker Desktop (macOS):**

| Check | Problem | Remediation |
|---|---|---|
| `network_mode: host` | Limited support — macOS VM boundary applies | Switch to bridge networking |
| `--cap-add NET_RAW` | May require `--privileged` on some macOS Docker versions | Test capability grants; fall back to privileged if needed |
| File system performance | Bind mounts from macOS to Linux VM are slow | Use named volumes for performance-critical paths |

**Native Linux:**

| Check | Problem | Remediation |
|---|---|---|
| `network_mode: host` | Works as expected | No remediation needed |
| Port < 1024 without root | Binding to privileged ports fails without root | Ensure computed ports are in unprivileged range (algorithm guarantees ≥ 10000) |

The Deployment Agent MUST log all platform-specific remediations to `DEPLOYMENT_NOTES.md`.

### 3.12 Step 12 — Connection Manifest Generation

**Owner:** Deployment Agent

After all services are healthy, auto-generate two files:

1. **`connection_manifest.yaml`** — the primary machine-readable artifact
2. **`CONNECTION_MANIFEST.md`** — rendered markdown for human and agent reading

#### `connection_manifest.yaml` Schema

```yaml
# Connection Manifest — auto-generated by Deployment Agent
# DO NOT EDIT MANUALLY — regenerated on every deployment
version: "1.0"

application:
  name: "bluescrub"                          # CONCORD registration name
  concord_version: "0.5"                     # CONCORD spec version
  generated_at: "2026-04-03T14:30:00Z"       # manifest generation timestamp
  host: "localhost"                           # deployment host
  base_port: 14854                            # computed base port
  port_algorithm: "name_weighted_hash"        # algorithm used

services:
  - name: "host-api"                          # human-readable service name
    url: "http://localhost:14854"              # full service URL
    health_endpoint: "http://localhost:14854/health"
    status: "healthy"                         # healthy | unhealthy | degraded
    container_name: "bluescrub-host"          # docker container name
    internal_port: 5000                       # port inside the container
    external_port: 14854                      # port on the host
    health_checked_at: "2026-04-03T14:30:05Z"

  - name: "analysis-service"
    url: "http://localhost:14855"
    health_endpoint: "http://localhost:14855/health"
    status: "healthy"
    container_name: "bluescrub-analysis"
    internal_port: 8630
    external_port: 14855
    health_checked_at: "2026-04-03T14:30:07Z"

sdk:
  base_url: "http://localhost:14854"          # SDK connection target
  required_env:                               # environment variables for SDK config
    BLUESCRUB_BASE_URL: "http://localhost:14854"
    BLUESCRUB_AGENT_CLASS: "your_agent_name"  # placeholder — agent fills in
    BLUESCRUB_TRUST_TIER: "1"                 # default trust tier

quick_verify:
  language: "python"
  code: |
    from bluescrub_sdk import BlueScrubClient
    client = BlueScrubClient("http://localhost:14854")
    assert client.health(), "Application is not reachable"

deployment_notes:
  port_remaps: []                             # any collision fallbacks applied
  platform_workarounds: []                    # OS-specific fixes applied
  dependency_fixes: []                        # build-time dependency resolutions
  generated_dockerignore: true                # whether .dockerignore was auto-generated
```

#### `CONNECTION_MANIFEST.md` Rendering

The markdown rendering MUST be auto-generated from `connection_manifest.yaml` — not hand-written separately. It includes:

- Service endpoint table with health status
- SDK configuration block (copy-pasteable environment variables)
- Quick-verify code snippet
- Deployment notes (port remaps, platform workarounds, dependency fixes)
- Timestamp of last generation

#### Manifest Rules

1. **Auto-generated, never hand-written.** The manifest is a deployment artifact, not documentation.
2. **Regenerated on every `docker compose up`.** Stale manifests are worse than no manifest — they point agents at dead endpoints.
3. **Placed in project root.** Both `connection_manifest.yaml` and `CONNECTION_MANIFEST.md` live in the project root, discoverable by convention.
4. **Referenced in SDK Integration Guide.** The SDK guide MUST link to the connection manifest, not hardcode endpoint URLs.
5. **Machine-readable first.** `connection_manifest.yaml` is the primary artifact. `CONNECTION_MANIFEST.md` is a convenience rendering. Consuming agents SHOULD parse the YAML.

---

---

## 4. Lessons Learned from Real Integration

This section captures pitfalls and best practices discovered during the first complete CONCORD integration (document processing domain).

### 4.1 Common Pitfalls

#### 4.1.1 Guard Parameter Dependencies

**Problem:** Guards that depend on intent parameters (e.g., `file_accessible`) cannot be fully evaluated in planning endpoints like `/operation-context` or `/budget/estimate`.

**Solution:** In planning endpoints, mark parameter-dependent guards as `passed: null` with reason "parameters unavailable for estimate". Only evaluate them during intent execution.

**Example from document processor:**
```python
# In budget estimate, guard evaluation returns:
{
  "guard_name": "file_accessible",
  "passed": null,
  "reason": "parameters unavailable for estimate"
}
```

#### 4.1.2 Session State Pollution in Tests

**Problem:** In-memory session stores shared across tests cause budget exhaustion and extension limits to affect subsequent tests.

**Solution:** Create fresh sessions for tests that need clean state. Use descriptive session IDs like `"session-test-budget-exhaustion"`.

**Example:**
```python
admission_pipeline.session_store.sessions["session-fresh"] = Session(
    session_id="session-fresh",
    trust_tier=1,
    expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
    budget_total=1000,
    budget_consumed=0,
    max_lifetime_at=datetime.now(timezone.utc) + timedelta(hours=8),
)
```

#### 4.1.3 Pipeline Stage Order Matters

**Problem:** Input validation must occur before guard evaluation, or guards fail on invalid parameters.

**Solution:** In `AdmissionPipeline.process_intent()`, validate parameters before evaluating guards. The correct order is:
1. Session resolution
2. Action resolution  
3. Trust gate
4. Budget gate
5. **Input validation** ← Must be here
6. **Guard evaluation** ← After validation
7. Idempotency check
8. Intent creation
9. Execution

#### 4.1.4 Schema Validation Errors Don't Fail Operations

**Problem:** Output schema validation in receipts records errors but doesn't prevent successful completion.

**Solution:** This is by design — agents receive partial results with validation warnings. Critical validation failures should be handled in the normalizer.

### 4.2 Best Practices Discovered

#### 4.2.1 Chained Actions for Complex Workflows

**Pattern:** For multi-step operations, create a single ActionContract that executes a sequence of sub-actions.

**Benefits:**
- Single budget deduction for complex workflow
- Atomic success/failure reporting
- Simplified agent planning (one intent instead of many)

**Example from document processor:**
```
ActionContract: document.process_chain
- Executes: scan → extract → convert → validate
- Cost: 200 (sum of individual costs)
- Output: Combined results from all steps + artifacts list
```

#### 4.2.2 File Artifact Preservation

**Pattern:** For actions that create files, include output paths in the result schema and track them in an `artifacts` array.

**Benefits:**
- Agents can reference created files in subsequent actions
- Cleanup and auditing become possible
- Results are self-documenting

**Example output:**
```json
{
  "conversion_success": true,
  "output_path": "/data/converted/sample.md",
  "artifacts": ["converted: /data/converted/sample.md"]
}
```

#### 4.2.3 Trust Tier Assignment

**Rule of thumb:**
- T0: Read-only operations with no side effects
- T1: Standard operations (most actions)
- T2+: Operations with significant consequences (deletion, deployment, financial impact)

**From document processor:**
- scan/extract/validate: T1 (standard analysis)
- convert: T2 (creates new files)
- process_chain: T1 (combines T1 operations)

### 4.3 Integration Checklist (Validated)

Use this checklist during integration. Each item has been tested in the document processor app.

#### Pre-Implementation
- [ ] Audit host application capabilities → ActionContracts
- [ ] Define JSON Schema Draft 2020-12 for all inputs/outputs
- [ ] Assign costs, trust tiers, and guards to each action
- [ ] Design guard callables for all guard names
- [ ] Plan executor functions (parameter translation)
- [ ] Design normalizers (schema-compliant outputs)

#### Implementation
- [ ] Register all ActionContracts
- [ ] Implement and register all guards
- [ ] Implement executors (delegate to business logic)
- [ ] Implement normalizers (transform raw outputs)
- [ ] Wire Admission Pipeline stages
- [ ] Implement runtime endpoints
- [ ] Add receipt validation

#### Testing
- [ ] Unit test each executor/normalizer
- [ ] Test pipeline with valid/invalid inputs
- [ ] Test all runtime endpoints
- [ ] Test error conditions (guards, budget, trust)
- [ ] Test session lifecycle and idempotency
- [ ] Test file-based workflows if applicable
- [ ] Validate JSON Schema enforcement
- [ ] Test receipt retrieval and validation

#### Deployment
- [ ] Cross-reference guards at startup
- [ ] Validate all schemas are Draft 2020-12
- [ ] Test with production-like data volumes
- [ ] Monitor for budget exhaustion patterns
- [ ] Set up logging for pipeline stage failures

**Mistake:** Declaring guards on every ActionContract but never implementing a Guard Registry or executing them in the pipeline.

**Result:** Agents query OperationContext, see guards listed, and believe preconditions are being enforced. They submit requests expecting governed `GUARD_FAILED` responses on precondition violations and instead receive raw crashes from the executor.

**Fix:** Guard names MUST map to callable functions in the Guard Registry. The GuardEvaluation stage (⑤) MUST execute them.

### 4.2 Schema Without Validation

**Mistake:** Defining `input_schema` and `output_schema` on ActionContracts but never validating parameters against them or normalizing output to match them.

**Result:** Agents submit intents with missing parameters and get raw crashes during execution. Agents receive unnormalized output they cannot parse.

**Fix:** InputValidation (⑥) MUST validate parameters. OutputNormalization (⑩) MUST transform output. The schemas are contracts, not documentation.

### 4.3 Executor as Passthrough

**Mistake:** Building the executor as `return host_function(**params)` — a thin wrapper that passes parameters through and returns raw results.

**Result:** Unclassified exceptions escape to the agent. Unpredictable output shapes. No cost accounting. No error catalog mapping.

**Fix:** The executor is a translation layer with three responsibilities: parameter translation, exception classification, and result packaging. See §3.3.

### 4.4 Multiple Pipelines

**Mistake:** Building a separate admission path for the dispatch endpoint, the batch endpoint, and the direct intent endpoint. The dispatch endpoint skips BudgetGate "for efficiency." The batch endpoint skips GuardEvaluation because "guards are checked on the first item."

**Result:** Governance bypasses. Budget overruns. Unguarded execution. The agent discovers that the same action behaves differently depending on which endpoint it uses.

**Fix:** One pipeline. Every entry point routes through it. See Admission Pipeline §3.6.

### 4.5 Timezone Silent Bug

**Mistake:** Using timezone-naive datetimes for `expires_at`, `created_at`, etc., or not normalizing datetimes after reading them from a database that strips timezone information (e.g., SQLite).

**Result:** Session expiry checks produce incorrect results. Sessions expire prematurely or run past their intended TTL. The bug is silent — it works in tests with in-memory databases and fails in production.

**Fix:** All datetimes use UTC-aware timestamps. After reading from persistence, re-attach UTC if the value is naive. All comparisons are between two UTC-aware values. See Admission Pipeline §7.1.

---

## 5. Contract Clarity Patterns

These patterns were surfaced during post-integration review of the first completed CONCORD integration. They address the hardest integration problems — not agent reasoning, but **contract clarity**: data shape, file semantics, runtime introspection, and outcome reporting. Each pattern is RECOMMENDED for any integration involving file I/O, multi-team collaboration, or human-facing output.

### 5.1 File-Backed Action Contracts

File-backed actions — those that accept or produce files as input/output — require explicit contract terms beyond JSON Schema field declarations. Without them, integrating teams will disagree on what a filename means, who creates the file, and what path scope is valid.

**Declare these terms on every file-backed ActionContract:**

| Term | What to Declare |
|---|---|
| **File role** | Is the parameter a reference to an already-materialized file, or a target location for output? Use `"role": "input_ref"` vs `"role": "output_target"`. |
| **Materialization owner** | Who creates the file: the calling agent, the host application, or the framework? Declare as `"materialized_by": "caller"` / `"host"` / `"framework"`. |
| **Ingest root** | The base path under which all file references must resolve. Declare as `"ingest_root": "/data/ingest"`. References outside this root MUST be rejected. |
| **Path scope rule** | Whether the action accepts absolute paths, relative paths, or only paths relative to the ingest root. Declare as `"path_scope": "relative_to_ingest_root"`. |
| **Volume contract** | If the file lives on a shared volume, name the volume and mount point. Agents and the host application must reference the same physical location. |

**Recommended `input_schema` pattern for file-backed actions:**

```json
{
  "type": "object",
  "properties": {
    "filename": {
      "type": "string",
      "description": "Filename relative to the ingest root (/data/ingest). File must already exist on the shared volume. Do not include the ingest root prefix.",
      "x-file-role": "input_ref",
      "x-materialized-by": "caller",
      "x-path-scope": "relative_to_ingest_root"
    }
  },
  "required": ["filename"]
}
```

**Guard pattern for file-backed actions:**

Every file-backed action SHOULD declare a `file_accessible` guard that resolves the full path at admission time:

```python
def guard_file_accessible(parameters, session):
    filename = parameters.get("filename", "")
    full_path = os.path.join(INGEST_ROOT, filename)
    if not os.path.exists(full_path):
        return GuardResult(passed=False, reason=f"File not found at {full_path}")
    return GuardResult(passed=True)
```

The guard MUST be registered and MUST run before execution. A missing file must produce `GUARD_FAILED`, not an executor crash.

**Shared-volume declaration in `connection_manifest.yaml`:**

```yaml
volumes:
  - name: "ingest"
    mount_path: "/data/ingest"
    host_path: "./data/ingest"
    access: "read-write"
    scope: "shared"
    note: "All file-backed action inputs must be placed here before invocation"
```

### 5.2 Canonical Output Envelopes

Every action must produce output in one of four envelope states. A universal framework should not leave each host application to invent its own shape for partial success or unavailability.

**The four canonical states:**

| State | When | Required Fields |
|---|---|---|
| `success` | The action completed and the domain goal was achieved | `status`, `result`, `receipt_id`, `domain_outcome` |
| `partial_success` | The action completed but some sub-goals failed | `status`, `result`, `warnings`, `receipt_id`, `domain_outcome` |
| `unavailable` | A dependency was unreachable; the action was not attempted | `status`, `error_code`, `agent_should`, `retry_after_seconds` |
| `failed` | The action was attempted and failed | `status`, `error_code`, `error_detail`, `agent_should`, `receipt_id` |

**Normalizer obligation:** Every normalizer MUST produce one of these four shapes. It MUST NOT return raw host application output.

**Recommended envelope schema:**

```json
{
  "status": "success | partial_success | unavailable | failed",
  "domain_outcome": "verified | unverified | not_applicable",
  "result": {},
  "warnings": [],
  "error_code": null,
  "error_detail": null,
  "agent_should": null,
  "receipt_id": "...",
  "retry_after_seconds": null
}
```

### 5.3 Transport Success vs. Domain Success

A governed receipt records that the pipeline completed — that the intent was admitted, executed, and a receipt was minted. This is **transport success**. It does not prove the domain goal was achieved.

**Examples of the distinction:**

| Action | Transport Success | Domain Success |
|---|---|---|
| `document.convert` | The conversion process ran to completion | The output file exists and is valid |
| `scan.run` | The scanner returned results | Findings match expected baseline |
| `report.submit` | The submission was acknowledged | The submission is visible in the target system |

**Implementation — add `domain_outcome` to every normalizer:**

```python
def normalize_document_convert(raw_output, action_contract):
    output_path = raw_output.get("output_path")
    file_exists = output_path and os.path.exists(output_path)

    return NormalizationResult(
        normalized={
            "status": "success" if file_exists else "partial_success",
            "domain_outcome": "verified" if file_exists else "unverified",
            "output_path": output_path,
            "conversion_success": raw_output.get("success", False),
        },
        warnings=[] if file_exists else ["Output file not found after conversion"]
    )
```

The normalizer is the right place to verify domain outcomes because it has access to the raw executor result and can perform post-execution checks (file existence, record counts, status codes from dependent systems).

### 5.4 Runtime Introspection Surface

Integrations require time-consuming debugging when there is no standard way to observe which configuration values, mounts, and capabilities are actually live at runtime. CONCORD integrations SHOULD expose a standard introspection endpoint.

**Recommended endpoint:** `GET /concord/introspect`

**Response schema:**

```json
{
  "concord_version": "0.5",
  "application": "your-app-name",
  "generated_at": "2026-04-17T00:00:00Z",
  "environment": {
    "YOUR_APP_BASE_URL": { "set": true, "value": "http://localhost:14854" },
    "YOUR_APP_API_KEY": { "set": true, "value": "[REDACTED]" },
    "INGEST_ROOT": { "set": true, "value": "/data/ingest" }
  },
  "mounts": {
    "/data/ingest": { "accessible": true, "writable": true, "file_count": 3 }
  },
  "actions": {
    "document.convert": { "available": true, "guards_passing": true },
    "scan.static_analysis": { "available": true, "guards_passing": false, "guard_failure": "service_healthy: scanner is unreachable" }
  },
  "capabilities": {
    "schema_version": "1.0.0",
    "deprecated_actions": [],
    "optional_features": ["batch", "dispatch"]
  }
}
```

**Rules:**
- Credential values MUST be redacted (`[REDACTED]`), but presence/absence MUST be reported.
- Mount accessibility MUST be tested at introspection time, not assumed from config.
- Guard pre-evaluation for each action SHOULD be included (with `null` handling for parameter-dependent guards, same as planning endpoints).
- This endpoint is read-only and does NOT flow through the admission pipeline.

### 5.5 Dependency Degradation Policy

When a dependency is unreachable or degraded, the host application's default behavior (crash, hang, return empty results) is not appropriate for governed agent execution. Each ActionContract SHOULD declare a degradation policy.

**Declare a degradation policy on each ActionContract:**

```json
{
  "degradation_policy": {
    "on_dependency_unreachable": "fail_closed",
    "on_dependency_degraded": "partial_success_allowed",
    "on_dependency_timeout": "fail_closed",
    "retry_eligible": true,
    "max_retries": 2
  }
}
```

**Policy options:**

| Policy | Behavior |
|---|---|
| `fail_closed` | Return `unavailable` immediately; do not attempt execution |
| `fail_open` | Attempt execution; return best-effort result with warnings |
| `partial_success_allowed` | Attempt execution; allow partial result envelope if some sub-goals fail |

**Common defaults by action family:**

| Action Family | Recommended Default Policy |
|---|---|
| `read` | `fail_open` — partial reads are often useful |
| `plan` | `fail_closed` — plans based on incomplete data are dangerous |
| `mutate` | `fail_closed` — partial mutations create inconsistency |
| `approve` | `fail_closed` — approvals without full context are unsafe |
| `deploy` | `fail_closed` — partial deployments are worse than none |
| `compensate` | `fail_open` — compensation should be attempted even under degradation |

**Framework obligation:** The GuardEvaluation stage (⑤) SHOULD map guard failures to the declared policy. A `fail_closed` action whose guard fails MUST return `GUARD_FAILED` with `"agent_should": "retry_after"` — not crash.

### 5.6 End-to-End Certification Pattern

A framework-level test recipe that both integrating teams can run independently surfaces contract mismatches before production.

**The golden path recipe:**

```
1. Submit input
   POST /intent/submit
   → Verify: receipt_id returned, status = "admitted"

2. Retrieve receipt (poll if async)
   GET /receipt/{receipt_id}
   → Verify: status = "completed"

3. Verify domain outcome
   → Verify: domain_outcome = "verified" (or "not_applicable")
   → Verify: result conforms to output_schema

4. Verify normalized output is renderable
   → Verify: status is one of the four canonical envelope states
   → Verify: result fields are present, typed correctly, non-null where required
```

**Certification criteria (both teams must agree on pass/fail):**

| Check | Pass Condition |
|---|---|
| Admission | receipt_id returned |
| Execution | `receipt.status` = "completed" or "failed" (not stuck) |
| Domain outcome | `domain_outcome` = "verified" for success cases |
| Schema conformance | result validates against `output_schema` without errors |
| Error behavior | Invalid inputs produce CONCORD error codes, not raw crashes |
| Trace correlation | `receipt_id` consistent across admission, execution, and normalized output |

Include this recipe in the integration test suite (see §6.4) as `test_golden_e2e_{action_name}`. Both teams can run it independently to verify their side of the contract.

### 5.7 Trace Correlation

End-to-end debugging requires that a single intent can be traced from admission through execution, normalization, and display using a consistent identifier.

**Mandatory correlation identifiers:**

| Identifier | Set By | Propagated To |
|---|---|---|
| `receipt_id` | ReceiptMinting (⑪) | Normalized output, audit log, external system receipts |
| `intent_id` | IntentCreation (⑧) | Executor, normalizer, all pipeline stage logs |
| `idempotency_key` | Caller | Idempotency store, receipt, audit log |
| `upload_id` / `job_id` | External system | Normalizer output, receipt `correlation` block |

**Required `correlation` block on every receipt:**

```json
{
  "receipt_id": "rcpt_abc123",
  "intent_id": "int_xyz789",
  "idempotency_key": "caller-provided-key",
  "correlation": {
    "external_job_id": "job_456",
    "external_upload_id": "upl_789",
    "pipeline_trace": [
      "session_resolved", "action_resolved", "trust_gate_passed",
      "budget_gate_passed", "validation_passed", "guards_passed",
      "idempotency_passed", "intent_created", "execution_completed",
      "normalization_completed", "receipt_minted"
    ]
  }
}
```

**Rules:**
- `intent_id` MUST be logged at every pipeline stage.
- If an external system returns a job ID or upload ID, the normalizer MUST surface it in the `correlation` block.
- Human-facing displays MUST show `receipt_id` so support teams can trace any reported issue.

### 5.8 Compatibility Metadata

When two teams evolve a shared integration independently, hidden field changes cause silent breakage. CONCORD integrations SHOULD declare schema compatibility metadata on every ActionContract.

**Recommended compatibility fields:**

```json
{
  "schema_version": "1.0.0",
  "input_schema_changes": [
    { "field": "filename", "status": "required", "since": "0.1.0" },
    { "field": "options", "status": "optional", "since": "0.3.0", "default": {} }
  ],
  "output_schema_changes": [
    { "field": "domain_outcome", "status": "required", "since": "0.4.0" },
    {
      "field": "legacy_status",
      "status": "deprecated",
      "since": "0.4.0",
      "removed_in": "1.0.0",
      "replaced_by": "domain_outcome"
    }
  ]
}
```

The `/actions` endpoint SHOULD include this metadata so consuming agents can inspect version compatibility without reading source code. Consuming agents SHOULD check `schema_version` on first connection and emit a warning if the integration schema is newer than the agent was built against.

### 5.9 Human-Facing Mirror Pattern

When a third-party UI mirrors an action's output, it SHOULD render directly from the canonical normalized object — not from a host-specific summary, a re-fetched API call, or a re-interpreted log entry. Rendering from anything other than the canonical receipt allows the UI to silently diverge from the governing record.

**Correct pattern:**

```
Agent submits intent
  → Pipeline produces receipt with normalized output
    → UI consumes receipt.result (the normalized object)
      → UI renders fields from receipt.result directly
```

**Incorrect patterns:**

```
❌ UI re-fetches from host application after agent completes
❌ UI parses agent's conversational summary to extract fields
❌ UI reads host application's internal database directly
❌ UI re-runs the action to get displayable output
```

If the normalizer omits fields the UI needs, the normalizer's `output_schema` is incomplete — fix the schema, not the UI.

**Checklist for mirror implementations:**

- [ ] UI reads `receipt.result` from `/receipt/{receipt_id}`
- [ ] UI does not re-fetch from the host application
- [ ] UI renders `domain_outcome` as a first-class status indicator
- [ ] UI shows `receipt_id` for support traceability
- [ ] UI handles all four canonical envelope states

---

## 6. Testing Strategy

### 6.1 Test the Governance Layer Independently

Write tests that exercise the CONCORD admission pipeline in isolation from the host application's business logic. Use a **mock executor** that returns canned results. This isolates governance correctness from legacy code behavior.

**Minimum governance test matrix:**

| Category | Test Cases |
|---|---|
| **Session** | Valid session, expired session, suspended session, not-found session, timezone-edge expiry |
| **Action** | Known action, unknown action, deprecated action |
| **Trust** | Sufficient tier, insufficient tier, boundary tier (exact match) |
| **Budget** | Sufficient budget, exhausted budget, circuit breaker open, no budget profile (stage skipped) |
| **Guards** | All pass, first fails, middle fails, last fails, unregistered guard name |
| **Input** | Valid params, missing required, wrong type, extra fields (warn-pass), empty params |
| **Idempotency** | New key, duplicate with completed intent (replay), duplicate with in-progress intent (conflict) |
| **Receipt** | Success receipt, failure receipt, zero-cost receipt, normalization-failure receipt |
| **Budget accounting** | Cost deducted on execution success, cost deducted on execution failure, cost NOT deducted on admission failure |

### 6.2 Test the Executor Separately

Once governance tests pass, test the executor's translation logic:

| Category | Test Cases |
|---|---|
| **Parameter translation** | Correct mapping, missing optional params (use defaults), type conversion |
| **Exception classification** | Each mapped exception produces correct error code, unmapped exception hits default handler |
| **Result packaging** | Output is serializable, output includes required fields, output handles empty/null returns |

### 6.3 Test the Normalizers Separately

For each ActionContract with an `output_schema`:

| Category | Test Cases |
|---|---|
| **Happy path** | Full output normalizes to correct schema shape |
| **Edge cases** | Empty result, partial data, timeout indicator, error-as-result |
| **Failure** | Completely unparseable output produces NormalizationResult with warnings, not an exception |

### 6.4 Integration Tests

Finally, end-to-end tests that wire everything together:

- Submit an intent through the full pipeline with a real executor → verify receipt and normalized output
- Submit an intent that should fail at each admission stage → verify correct error code and `agent_should` guidance
- Submit a dispatch with multiple sub-actions → verify each routes through the pipeline independently
- Expire a session mid-workflow → verify clean failure and session refresh mechanism

### 6.5 Executor Registration Gate (v0.5.1 — Normative)

Before an executor is registered in the ActionContract registry, it MUST pass a validation suite. An executor that fails its own output contract is a governance violation — it produces execution failures inside the admission pipeline that agents must treat as availability events rather than the coding bugs they actually are.

**Pre-registration test requirements:**

1. **Output contract conformance:**
   - Execute the executor with valid parameters
   - Assert the output conforms to the ActionContract's `output_schema`
   - If the executor writes to persistent storage, assert no `NULL` values reach non-nullable columns

2. **Exception mapping completeness:**
   - Trigger each exception class in the exception mapping table
   - Assert the correct CONCORD error code is produced for each
   - Trigger an unmapped exception → assert the default handler catches it and produces `EXECUTION_FAILED`

3. **Normalizer round-trip:**
   - Feed the executor's actual output to the normalizer
   - Assert the normalized output conforms to `output_schema`
   - Assert the normalizer handles edge cases (empty results, partial data)

**Gate enforcement:** The pipeline initialization SHOULD refuse to register an ActionContract whose executor has not passed these tests. In development, a warning is acceptable; in production, it SHOULD be a hard failure.

**Rationale:** This gate was motivated by a real integration where an executor's database insert failed at runtime with a `NOT NULL` constraint violation on a timestamp field. The field was required by the database schema but not populated by the executor. This was discovered through a live CONCORD execution failure — pre-registration testing would have caught it at deploy time.

---

## 7. Checklist

Before declaring the integration complete, verify:

**Governance (Phases 1–3):**

- [ ] Every host application capability has a corresponding ActionContract
- [ ] Every ActionContract has `input_schema` and `output_schema` (even if minimal)
- [ ] Every guard name declared on any ActionContract has a registry entry
- [ ] Every guard callable conforms to the Guard Contract signature
- [ ] The executor catches all host exceptions and maps to CONCORD error codes
- [ ] The exception mapping table includes a default/catch-all entry
- [ ] Every ActionContract with `output_schema` has a normalizer that conforms to it
- [ ] The admission pipeline implements all 11 stages in order
- [ ] All entry points route through the same pipeline
- [ ] Budget is deducted at ReceiptMinting, not at BudgetGate
- [ ] All datetimes are UTC-aware and timezone-safe through persistence round-trips
- [ ] Governance tests pass with mock executor
- [ ] Executor tests pass with mock host functions
- [ ] Normalizer tests pass with sample outputs
- [ ] `agent_should` is present on every error response
- [ ] No raw exceptions, tracebacks, or unstructured error messages reach the agent consumer

**Contract Clarity (§5 Patterns — Recommended):**

- [ ] File-backed actions declare file role, materialization owner, ingest root, and path scope in `input_schema`
- [ ] File-backed actions declare shared volume in `connection_manifest.yaml`
- [ ] File-backed actions have a `file_accessible` guard registered and executed
- [ ] Every normalizer produces one of the four canonical envelope states (`success`, `partial_success`, `unavailable`, `failed`)
- [ ] Every normalizer includes `domain_outcome` field (`verified` / `unverified` / `not_applicable`)
- [ ] `GET /concord/introspect` endpoint implemented with env, mounts, action availability, and guard pre-evaluation
- [ ] Every ActionContract with external dependencies declares a `degradation_policy`
- [ ] Golden E2E test (`test_golden_e2e_{action_name}`) implemented and passes for every action
- [ ] Every receipt includes `intent_id`, `idempotency_key`, and `correlation` block
- [ ] External job/upload IDs surfaced in receipt `correlation` block by normalizer
- [ ] ActionContracts include `schema_version` and `input_schema_changes` / `output_schema_changes`
- [ ] `/actions` endpoint exposes compatibility metadata
- [ ] Human-facing UI reads `receipt.result` from `/receipt/{receipt_id}`, not from re-fetch or re-parse
- [ ] UI renders `domain_outcome` as first-class status and shows `receipt_id`

**Post-Deploy Readiness (Phase 4):**

- [ ] Deterministic port assignment applied (ports derived from application name)
- [ ] `docker-compose.yml` host port bindings use computed ports, not defaults
- [ ] `.dockerignore` exists in every build context directory
- [ ] `docker compose build` completes without errors
- [ ] All containers start and pass health probes within timeout
- [ ] Platform-specific checks passed (no `network_mode: host` on Docker Desktop, etc.)
- [ ] `connection_manifest.yaml` generated in project root with correct schema
- [ ] `CONNECTION_MANIFEST.md` auto-rendered from YAML manifest
- [ ] SDK integration guide references the connection manifest, not hardcoded URLs
- [ ] `DEPLOYMENT_NOTES.md` documents all remaps, fixes, and workarounds applied
- [ ] `/deploy/status` endpoint returns healthy status for all services

---

## 8. MCP Integration (Optional)

If the host application needs to be consumable by MCP-aware agents (Claude Desktop, Cursor, custom agent frameworks), an optional **MCP Adapter Profile** is available:

📄 **[CONCORD_v0.5_MCP_Adapter_Profile.md](CONCORD_v0.5_MCP_Adapter_Profile.md)**

The MCP Adapter Profile defines how to expose a CONCORD-governed application as an MCP server while preserving full admission pipeline governance. It includes a formal **MCP Readiness Tier** system (Experimental / Beta / Production) so teams can declare their implementation maturity and consuming agents can calibrate expectations. It covers:

- **Session binding** — mapping MCP connections to CONCORD Sessions with token-based AgentClass assignment and fail-closed semantics
- **Tool discovery** — exposing ActionContracts as MCP tools with `inputSchema`, `outputSchema`, and standard annotations
- **Tool invocation** — routing every MCP `tools/call` through the full 11-stage admission pipeline
- **Error handling** — mapping CONCORD admission failures to MCP tool execution errors (`isError: true`) with `agent_should` guidance in `structuredContent`
- **Receipt transport** — returning receipts in MCP `structuredContent` validated against the tool's `outputSchema`
- **Planning resources** — exposing OperationContext, budget status, and deploy health as free MCP Resources (no admission pipeline, no budget cost)
- **MCP readiness tiers** — Experimental (8 tests, basic governance), Beta (18 tests, governance-complete), Production (22 tests, fleet-safe) with honest claim language for each tier
- **Capability advertisement governance** — normative rule that a bridge MUST NOT advertise MCP capabilities it has not implemented; safe `initialize` capability objects defined per tier
- **Scenario conformance tests** — 22 conformance tests across three validated scenarios (Claude Desktop, Cursor long-lived sessions, enterprise cross-app orchestration)

**Prerequisites:** The MCP Adapter Profile requires a complete CONCORD integration (Steps 1–12 in §3 above). The MCP bridge is an additional entry surface — it does not replace or modify the core admission pipeline.

**Key principle:** MCP is "just another EntryPoint." The bridge translates MCP protocol operations into CONCORD Intents. Every governance guarantee (trust gates, budget gates, guards, receipts) is enforced identically to native CONCORD consumers.

---

*End of Integration Guide. This document is normative for all CONCORD integrations.*

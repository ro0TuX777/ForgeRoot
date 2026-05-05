# ForgeTranscript: Agent Reasoning Observability Subsystem
**Status:** Proposal | **Author:** ForgeRoot Architecture Team | **Target:** Phase 2 Integration

---

## 1. Problem Statement

ForgeRoot's existing audit infrastructure captures **governance events** — what was admitted, decided, and verified — but provides no structured visibility into the **cognitive output** of agents: their reasoning chains, intermediate proposals, tool-call conversations, rejected alternatives, and natural-language justifications.

This creates a critical observability gap:

| What We Can Answer Today | What We Cannot Answer |
|---|---|
| Was this agent admitted? | *What did the agent reason before proposing this action?* |
| Was the action allowed or denied? | *What alternatives did the agent consider and discard?* |
| Did the change pass verification? | *What was the agent's internal chain-of-thought?* |
| What evidence was recorded? | *What tool outputs did the agent consume mid-task?* |
| Was the session revoked? | *What did the agent say to the user during execution?* |

Without this layer, incident responders reconstruct *what happened* from decision chains but cannot determine *why it happened*. Compliance officers can prove governance was enforced but cannot demonstrate the reasoning was sound. Operators can see verdicts but cannot understand the cognitive path that produced them.

**ForgeTranscript** closes this gap by capturing, indexing, and surfacing the full natural-language and tool-interaction output of every governed agent session as a first-class, tamper-evident, queryable record.

---

## 2. Architectural Position

ForgeTranscript occupies the **observability plane** between the agent's cognitive execution and ForgeRoot's existing governance control layers.

```
  ┌─────────────────────────────────────────────────────────┐
  │                    Agent Runtime                        │
  │  ┌──────────┐  ┌──────────┐  ┌────────────────────┐   │
  │  │ Reasoning│  │ Tool Call│  │ Intermediate Output│   │
  │  │ Chains   │  │ Results  │  │ & Proposals        │   │
  │  └────┬─────┘  └────┬─────┘  └─────────┬──────────┘   │
  │       │              │                  │               │
  └───────┼──────────────┼──────────────────┼───────────────┘
          │              │                  │
          ▼              ▼                  ▼
  ┌─────────────────────────────────────────────────────────┐
  │               ForgeTranscript Capture Layer             │
  │                                                         │
  │   TranscriptEmitter → SegmentClassifier → SessionLog   │
  │                                                         │
  └──────────────────────────┬──────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       ┌────────────┐ ┌───────────┐ ┌─────────────┐
       │ Transcript │ │ ForgeLedger│ │ SIEM / OCSF │
       │ Reader UI  │ │ Evidence  │ │ Forwarding   │
       │ (Human)    │ │ Chain     │ │ (Machine)    │
       └────────────┘ └───────────┘ └─────────────┘
```

**Key integration points:**
- **CONCORD** — SessionID and AgentIdentity anchor every transcript to its admission context
- **ForgeLedger** — Transcript segments are HMAC-SHA256 chained into the existing evidence trail
- **ForgeGate** — DecisionRecords are cross-referenced with the reasoning that produced the proposal
- **Azul** — ComprehensionReviews are embedded within the transcript timeline, not isolated artifacts

---

## 3. Core Concepts

### 3.1 Transcript Session

A `TranscriptSession` is the top-level container, bound 1:1 to a CONCORD-admitted session. It is opened when CONCORD issues an admission receipt and sealed when the session terminates or is revoked.

```json
{
  "transcript_id": "ft-a8c3e...",
  "session_id": "concord-session-7f2b...",
  "agent_id": "agent-alpha-01",
  "trust_tier": "T2",
  "opened_at": "2026-05-05T04:00:00Z",
  "sealed_at": null,
  "segment_count": 0,
  "chain_head": null
}
```

### 3.2 Transcript Segments

Each discrete unit of agent output is captured as a typed `TranscriptSegment`. Segments are classified on ingest:

| Segment Type | Content | Source |
|---|---|---|
| `REASONING` | Chain-of-thought, planning, internal deliberation | Agent cognitive output |
| `PROPOSAL` | Concrete action proposals before ForgeGate evaluation | Agent → ForgeGate boundary |
| `TOOL_CALL` | Tool invocation request + parameters | Agent → tool interface |
| `TOOL_RESULT` | Tool execution output returned to agent | Tool → agent interface |
| `USER_EXCHANGE` | Natural-language messages between agent and operator | Agent ↔ user interface |
| `DECISION_REF` | Inline reference to a ForgeGate DecisionRecord | ForgeGate → transcript link |
| `COMPREHENSION` | ComprehensionReview output from Azul verification | Azul → transcript link |
| `SYSTEM_EVENT` | Budget warnings, trust escalations, circuit-breaker triggers | CONCORD / system |
| `REJECTION` | Discarded alternatives with agent's stated reason | Agent cognitive output |
| `ERROR` | Failures, exceptions, and recovery attempts | Runtime |

### 3.3 Tamper-Evident Chaining

Every segment is HMAC-SHA256 chained to its predecessor within the session, extending the ForgeLedger evidence model:

```
Segment[n].hash = HMAC-SHA256(
    key = session_signing_key,
    data = Segment[n].content || Segment[n].type || Segment[n].timestamp || Segment[n-1].hash
)
```

Modifying or deleting any segment invalidates the chain from that point forward.

### 3.4 Redaction Policy

ForgeTranscript inherits ForgeLedger's ingest-time redaction framework. Sensitive content (memory vectors, credentials, PII) is redacted at capture time based on the agent's trust tier and the session's classification level. Redacted segments retain their chain position and hash integrity — the redaction itself is an auditable event.

---

## 4. TranscriptReader — Human Interface

The TranscriptReader is the operator-facing interface for browsing, searching, and analyzing agent transcripts.

```
┌─────────────────────────────────────────────────────────────────┐
│  ForgeTranscript Reader                              [Search]  │
├──────────────────┬──────────────────────────────────────────────┤
│                  │                                              │
│  SESSION LIST    │  TRANSCRIPT TIMELINE                        │
│                  │                                              │
│  ● agent-alpha   │  04:00:12 [REASONING]                       │
│    Session 7f2b  │  "Analyzing the target module for           │
│    T2 | Active   │   dependency conflicts before proposing     │
│    42 segments   │   the patch..."                             │
│                  │                                              │
│  ○ agent-beta    │  04:00:15 [TOOL_CALL] read_file             │
│    Session a3c1  │  { "path": "src/core/engine.py" }           │
│    T1 | Sealed   │                                              │
│    18 segments   │  04:00:16 [TOOL_RESULT]                     │
│                  │  "class CoreEngine: ..."  (truncated)       │
│  ○ agent-gamma   │                                              │
│    Session e9f0  │  04:00:22 [PROPOSAL]                        │
│    T3 | Revoked  │  "Refactor CoreEngine.route() to accept     │
│    7 segments    │   provider_override parameter"              │
│                  │                                              │
│                  │  04:00:22 [DECISION_REF] → DR-4a8f          │
│                  │  ForgeGate: ALLOW (no modifications)        │
│                  │                                              │
│  FILTERS:        │  04:00:31 [REJECTION]                       │
│  □ REASONING     │  "Considered direct monkey-patch but        │
│  ☑ PROPOSAL      │   rejected — violates ownership boundary    │
│  ☑ TOOL_CALL     │   of ProviderRegistry"                     │
│  ☑ DECISION_REF  │                                              │
│  □ ERROR         │  04:00:45 [USER_EXCHANGE]                   │
│                  │  Agent → User: "I've completed the refactor │
│                  │  across 3 files. Ready for review."         │
│                  │                                              │
└──────────────────┴──────────────────────────────────────────────┘
```

**Key capabilities:**
- **Timeline view** — Chronological segment stream with type-based color coding and icons
- **Segment filtering** — Toggle segment types on/off to focus on reasoning, proposals, errors, etc.
- **Cross-reference navigation** — Click a `DECISION_REF` to jump to the full DecisionRecord in ForgeLedger
- **Search** — Full-text search across all segments within a session or across all sessions
- **Diff view** — Side-by-side comparison of what the agent proposed vs. what ForgeGate allowed
- **Export** — Download full transcript as JSON, Markdown, or PDF for offline review

---

## 5. Five Use Cases

### Use Case 1: Post-Incident Forensic Reconstruction

**Persona:** Security Incident Responder
**Trigger:** An agent's session was revoked by CONCORD after an anomaly detector flagged suspicious behavior. The team needs to understand what the agent was doing and why.

**Current gap:** The incident responder can see that the session was revoked (CONCORD receipt) and that certain actions were denied (ForgeGate DecisionRecords), but they cannot see the agent's reasoning that led to those actions, what information the agent consumed from tool calls, or what intermediate plans it considered.

**With ForgeTranscript:**

1. Responder opens the TranscriptReader and locates the revoked session by agent ID
2. They see the full timeline: the agent's initial reasoning, the tool calls it made to gather information, the proposals it generated, and the ForgeGate decisions inline
3. They identify the exact segment where the agent's reasoning shifted — it consumed an unexpected tool result that altered its plan
4. They trace the `REJECTION` segments to see what the agent considered but discarded — revealing the agent explored two unauthorized action paths before settling on the flagged one
5. They export the transcript as evidence for the incident report, with the HMAC chain proving no segments were altered post-capture

**Value:** Reduces incident investigation from hours of log correlation to minutes of transcript reading. Provides **causal narrative**, not just event sequence.

---

### Use Case 2: Governance Compliance Audit

**Persona:** Compliance Officer / External Auditor
**Trigger:** A regulated organization must demonstrate to auditors that AI-driven engineering actions were not only governed but that the reasoning behind those actions was sound, documented, and reviewable.

**Current gap:** ForgeRoot can prove governance was enforced (admission receipts, decision records, evidence indexes). But auditors increasingly ask: *"Show me the agent's reasoning. How do you know it wasn't hallucinating a justification?"* The existing evidence trail answers *what* but not *why*.

**With ForgeTranscript:**

1. Auditor requests all transcript sessions for a specific time period or project scope
2. They filter to `REASONING` + `PROPOSAL` + `DECISION_REF` segments to see the cognitive-to-governance pipeline
3. For each approved action, they can read the agent's stated reasoning and verify it aligns with the proposal that ForgeGate evaluated
4. They verify the HMAC chain integrity to confirm no transcript segments were inserted, modified, or deleted after capture
5. They cross-reference `COMPREHENSION` segments with Azul verdicts to confirm the agent's structural explanation was genuine, not post-hoc

**Value:** Transforms compliance from *"we had controls"* to *"we have full cognitive traceability."* Meets emerging regulatory expectations for AI decision explainability.

---

### Use Case 3: Agent Quality Evaluation & Tuning

**Persona:** AI/ML Engineer responsible for agent performance
**Trigger:** An agent consistently produces valid but suboptimal proposals — choosing longer refactoring paths, missing obvious tool shortcuts, or generating verbose explanations. The team needs to understand *how* the agent reasons to improve its prompts, fine-tuning data, or tool descriptions.

**Current gap:** Azul captures the final verdict (PASS/FAIL/WARN_DARK_CODE) and ForgeGate captures the decision, but neither reveals the agent's intermediate reasoning quality. The team cannot see where the agent wasted cycles, explored dead ends, or misunderstood tool capabilities.

**With ForgeTranscript:**

1. Engineer queries all sessions for a specific agent profile over the last 30 days
2. They filter to `REASONING` + `REJECTION` + `TOOL_CALL` segments to study the agent's decision-making patterns
3. They identify that the agent consistently calls `read_file` on 12+ files before proposing changes — when the ForgeScaffold blueprint (available via `SYSTEM_EVENT`) already contained the structural map
4. They spot repeated `REJECTION` segments where the agent considers the correct approach but talks itself out of it due to a prompt ambiguity
5. They use these transcript patterns to refine the agent's system prompt and update tool descriptions in the action catalog

**Value:** Provides **cognitive telemetry** for agent improvement. Turns transcript data into actionable training signal without waiting for downstream failures.

---

### Use Case 4: Real-Time Operator Situational Awareness

**Persona:** DevOps / Platform Operator monitoring autonomous agent workflows
**Trigger:** Multiple agents are executing governed workflows in parallel across a production environment. The operator needs to understand what each agent is currently doing, what it's planning next, and whether any agent is approaching a risky decision boundary.

**Current gap:** The operator can see CONCORD admission status and ForgeHarbor environment assignments, but has no visibility into the agent's current cognitive state — what it's reasoning about, what tool results it just consumed, or what proposal it's about to submit to ForgeGate.

**With ForgeTranscript:**

1. Operator opens the TranscriptReader dashboard showing all active sessions
2. Live-streaming segments appear in real-time as each agent reasons, calls tools, and generates proposals
3. The operator notices `agent-gamma` just received an unexpected `TOOL_RESULT` from a dependency scanner showing 14 critical vulnerabilities — and its `REASONING` segment shows it's planning a broad remediation patch
4. The operator preemptively flags the session for human review before the proposal reaches ForgeGate, avoiding a large blast-radius change during peak hours
5. Meanwhile, `agent-alpha`'s transcript shows steady, well-scoped reasoning — the operator lets it proceed autonomously

**Value:** Shifts operator posture from **reactive** (reviewing after verdicts) to **proactive** (intervening during reasoning). Enables informed human-in-the-loop decisions at the right moment.

---

### Use Case 5: Cross-Agent Collaboration Tracing

**Persona:** System Architect overseeing multi-agent orchestration
**Trigger:** A complex workflow involves three agents collaborating: one discovers the action path (ForgeAtlas), another executes the change, and a third verifies it (Azul). The architect needs to trace how information flowed between agents and whether any agent operated on stale or misunderstood context from another.

**Current gap:** Each agent's governance events are independently recorded, but there is no unified view showing how one agent's output became another agent's input. The architect cannot trace cognitive handoffs or identify where context was lost between agents.

**With ForgeTranscript:**

1. Architect opens the TranscriptReader and links three related sessions by their shared workflow ID
2. They use the **multi-session timeline** view to see all three agents' segments interleaved chronologically
3. They trace a `TOOL_RESULT` in Agent A's transcript that becomes a `REASONING` input in Agent B's transcript — and spot that Agent B misinterpreted a field from Agent A's output
4. They identify that Agent C (the verifier) flagged a `WARN_DARK_CODE` because Agent B's `COMPREHENSION` segment didn't match the structural reality — and the root cause traces back to the context loss at the A→B handoff
5. They use this analysis to add a schema validation contract at the agent handoff boundary, preventing future context degradation

**Value:** Enables **end-to-end cognitive tracing** across multi-agent workflows. Surfaces information loss at agent boundaries that governance events alone cannot reveal.

---

## 6. Integration with Existing ForgeRoot Subsystems

| Subsystem | Integration Point |
|---|---|
| **CONCORD** | Session creation/revocation events open/seal transcript sessions. AgentID and TrustTier anchor every transcript. |
| **ForgeAtlas** | Discovery queries and filtered results are captured as `TOOL_CALL` / `TOOL_RESULT` segments, showing what the agent searched for and what it was allowed to see. |
| **ForgeGate** | Every `DecisionRecord` is embedded as a `DECISION_REF` segment in the transcript timeline, creating a causal link between reasoning and governance. |
| **ForgeHarbor** | Environment assignment and lifecycle events appear as `SYSTEM_EVENT` segments. Execution output from sandboxed runs feeds back as `TOOL_RESULT` segments. |
| **ForgeScaffold** | Blueprint generation and apply-pipeline events appear in the transcript. Patchset proposals are captured as `PROPOSAL` segments with full diff context. |
| **ForgeLedger** | Transcript segments extend the HMAC-SHA256 evidence chain. ForgeTranscript is a **producer** into the ForgeLedger evidence infrastructure. |
| **Azul** | `ComprehensionReview` output is captured as a `COMPREHENSION` segment. The Azul verdict references the transcript session for full cognitive context. |

---

## 7. Implementation Phases

### Phase 1 — Capture & Store (Foundation)
- Implement `TranscriptEmitter` adapter interface
- Define segment schema and classification taxonomy
- Implement HMAC-SHA256 chaining extending ForgeLedger
- Integrate emitters at CONCORD session boundary and ForgeGate proposal boundary
- Store segments in append-only ledger with session indexing

### Phase 2 — TranscriptReader UI (Human Access)
- Build session list with status indicators (active/sealed/revoked)
- Implement chronological timeline view with segment type filtering
- Add cross-reference navigation to ForgeLedger DecisionRecords
- Implement full-text search across sessions
- Add export capability (JSON / Markdown / PDF)

### Phase 3 — Live Streaming & Operator Dashboard (Real-Time)
- Implement WebSocket-based live segment streaming
- Build multi-session dashboard for parallel agent monitoring
- Add operator intervention hooks (flag session, request pause)
- Integrate with cockpit operational dashboard

### Phase 4 — Analytics & Training Signal (Intelligence)
- Implement cross-session pattern analysis for agent quality evaluation
- Build multi-session timeline view for cross-agent collaboration tracing
- Generate distillation-ready training pairs from high-quality reasoning chains
- Integrate with Azul's XP and training pair emission pipeline

---

## 8. Security Considerations

| Concern | Mitigation |
|---|---|
| **Sensitive content in reasoning** | Ingest-time redaction inherited from ForgeLedger; trust-tier-scoped visibility |
| **Transcript tampering** | HMAC-SHA256 chaining; append-only storage; chain validation on read |
| **Unauthorized transcript access** | CONCORD-gated access; operators must hold appropriate TrustTier to view sessions at or below their clearance |
| **Storage volume** | Configurable retention policies per trust tier; segment compression; cold-tier archival for sealed sessions |
| **Oracle/model leakage** | Inference isolation principles from Addendum B apply; transcript capture occurs at the boundary, not inside the model |

---

## 9. Success Criteria

ForgeTranscript is successful when:

1. **Every governed agent session** produces a complete, tamper-evident transcript from admission to termination
2. **An incident responder** can reconstruct an agent's full cognitive narrative in under 5 minutes using the TranscriptReader
3. **A compliance auditor** can verify reasoning-to-governance alignment without requesting additional evidence
4. **An operator** can observe live agent reasoning and intervene before a risky proposal reaches ForgeGate
5. **An ML engineer** can extract actionable quality signals from transcript patterns without deploying custom instrumentation

---

*ForgeTranscript — Because governance without cognitive visibility is governance in the dark.*

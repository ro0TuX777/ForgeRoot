# ForgeRoot AI Developer Questionnaire (AIDQ)

**Purpose:** Capture project-specific constraints so integrators can **phase adoption**, **cherry-pick** ForgeRoot components, or **substitute** org-owned systems **without accidentally breaking assurance invariants**.

**How to use:** Copy this file into your project as `ForgeRoot/integration_profile.yaml` companion notes, or fill inline. Every “defer / substitute” answer should list a **compensating control** and a **target date** or **risk acceptance owner**.

---

## Section A — Project and harness context

1. **Project name / repo:**  
2. **Primary integrator contact (human or team):**  
3. **One-paragraph mission:** What does your agent harness do for users?  
4. **Languages & runtime:** (e.g., Python worker, TS service, JVM, hybrid)  
5. **Deploy target:** laptop-only, VPC, SaaS tenant, regulated enclave—describe network assumptions.  
6. **Throughput & latency posture:** Typical parallel agent count; admission/eval latency budget (ms / s). Hard real-time?

---

## Section B — Trust, identity, and responsibility

7. **Agent identity model:** How are agents instantiated (ephemeral IDs, named agents, delegated human OIDC)?  
8. **Trust tiers:** Enumerate tiers you need (even if tentative). Which tiers may spend budget or touch prod?  
9. **Humans vs agents on the critical path:** Where is HITL mandatory vs optional?  
10. **Kill-switch / revocation:** Who can suspend sessions; what must propagate in <1s vs “best effort”?  
11. **Budget semantics:** Monetary, token, CPU, concurrency slots—what is enforced where?

---

## Section C — Action surface & discovery model

12. **Tool / action cardinality:** Rough count of discrete tools/services; steady growth rate.  
13. **Discovery preference:** Must use ForgeAtlas semantic discovery, acceptable to use curated static manifests, or hybrid?  
14. **Strict invariant check:** Confirm you accept: *agents must not discover actions they cannot admit.* If no, justify and document compensating control.  
15. **Highest-risk actions:** List destructive or production-touching capabilities (even if hypothetical).  
16. **Circuit breakers:** Per action family IDs you need (`CIRCUIT_OPEN`-style freezes).

---

## Section D — Policy and enforcement (ForgeGate plane)

17. **Policy source:** In-repo rules, DB, OPAL/Rego-style, custom—what evaluates allow/deny?  
18. **Separation guarantee:** Confirm model output is treated as proposal only downstream of policy. Exceptions?  
19. **Signals available at decision time:** Budget state, anomaly scores, deployment phase, blast-radius hints—list all.  
20. **Modification / shaping:** When policy returns MODIFY, what transformers are acceptable (truncate args, downgrade tool, reroute sandbox)?  
21. **Escalations:** ForgeGate escalation → which queue (Slack, Jira, on-call)—define SLA.

---

## Section E — Runtime isolation (ForgeHarbor plane)

22. **Preferred provider:** Containers today; microVM/TEE later; Kubernetes-only—state constraints.  
23. **Shared vs dedicated hosts:** Regulatory need for pinned isolation or noisy-neighbor isolation?  
24. **Stateful side effects:** What must persist across steps vs never persist?  
25. **Cold start tolerance:** If warm pool unavailable, interim plan (queue, degraded mode, deny)?  
26. **Secret injection into sandboxes:** How secrets reach runs without poisoning host.

---

## Section F — Codebase mutation (ForgeScaffold plane)

27. **Do agents mutate repos or live systems?** Y/N — if yes, which?  
28. **Blueprint fidelity:** Minimal (module list) vs full dataflow/contracts—pick target maturity.  
29. **Legacy / unmapped zones:** Accept “Auto-Scaffold-Before-Mutate” divert (whitepaper)—Y/N / timeline.  
30. **Evidence index consumer:** CI, security, auditors—who reads structural evidence?  
31. **Reviewer model:** Roles for patch review; required reviewers per trust tier.

---

## Section G — Behavioral verification & dark code (Azul plane)

32. **Need Azul-tier verdicts:** Block release without PASS? WARN handling? Pilot only?  
33. **Evaluation assets:** Existing CI, custom ForgeWorks pipelines, perf/security suites—enumerate.  
34. **Dark Code / comprehension gate:** Will you enforce structured explanations vs scaffold maps—always, sampled, trust-tier gated?  
35. **Oracle separation:** Inference for verification isolated from codegen models—possible in your infra?  

---

## Section H — Evidence, compliance, observability

36. **ForgeLedger posture:** Mandatory, phased, optional, not applicable—explain.  
37. **FID status:** Using `forgeledger_integration_template.md` → link to repo path / doc ID when started.  
38. **ForgeLedger supplementary form:** Completing `ForgeLedger/third_party_integration_questionnaire.md` in addition — Y/N.  
39. **Sensitive data classes:** PII/PHI/credentials/IP—enumerate; default redaction owner.  
40. **Forbidden fields in telemetry:** Explicit list (raw prompts, customer payloads, secrets).  
41. **Retention & residency:** Where evidence may physically live; encryption at rest assumptions.  
42. **SIEM / OCSF:** Required mapping now vs later—tooling (Splunk, Elastic, DD, Sentinel, …).  

---

## Section I — Phased rollout decision (pick one path, customize)

Answer with **FULL / PARTIAL / DEFERRED / SUBSTITUTE (name)** for each component.

| Component | Choice | Substitution / stub | Evidence you will produce |
|-----------|--------|---------------------|---------------------------|
| CONCORD | | | |
| ForgeAtlas | | | |
| ForgeGate | | | |
| ForgeHarbor | | | |
| ForgeScaffold | | | |
| Azul | | | |
| ForgeLedger / FID | | | |

**Partial stack risks:** Narrate worst-case coupling if skipped layers remain open for >N days.

---

## Section J — Open gaps and waiver log

Track explicit waivers—these become audit debt.

| ID | Gap | Risk | Compensating control | Owner | Deadline |
|----|-----|------|----------------------|-------|----------|
| W1 | | | | | |

---

## Section K — Sign-off stub

**Integration profile approved by:** ___  
**Date:** ___  

**ForgeRoot phased target:** MID Phase ___ through ___ (see `forge_root_master_integration.md`)

---

### Optional machine-readable appendix (example YAML fragment)

Teams may mirror Section I programmatically:

```yaml
forge_root_integration_profile:
  project: ""
  phased_target: ["0", "1", "2"]
  components:
    concord: { mode: FULL, substitution: null }
    forge_atlas: { mode: PARTIAL, substitution: "static_manifest_v1" }
    forge_gate: { mode: FULL, substitution: null }
    forge_harbor: { mode: SUBSTITUTE, substitution: "k8s_job_isolation_beta" }
    forge_scaffold: { mode: DEFERRED }
    azul: { mode: PILOT_ONLY }
    forge_ledger_fid: { mode: PHASED }
  waivers: []
```

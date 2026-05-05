# CONCORD Integration Onboarding — Agent Briefing Template

**Template Version:** 0.5.0 | **Date:** April 2026  
**Purpose:** Provide to any AI agent before it begins integrating CONCORD governance into a host application.  
**Usage:** Copy this template, fill in every `{PLACEHOLDER}` section, and place the completed file in the host application's repository root. The agent reads this file first.

---

## 0. How to Use This Document

You are an AI agent about to integrate CONCORD governance into an existing application. This document orients you to:
1. What the application does and how it's built
2. What CONCORD artifacts already exist (if any)
3. What spec documents to read, and in what order
4. What's already been done, what's broken, and what decisions have been made

**Read this document first. Then read the specs it references. Then begin work.**

---

## 1. Application Overview

### 1.1 What This Application Does
> {DESCRIPTION — 2-3 sentences. What does the app do? Who are its users? What is its primary value?}

### 1.2 Technology Stack
| Layer | Technology |
|---|---|
| Language | {e.g., Python 3.12} |
| Framework | {e.g., Flask, Django, Express, Spring} |
| Database | {e.g., SQLite, PostgreSQL, MongoDB} |
| ORM / Data Layer | {e.g., SQLAlchemy, Django ORM, Prisma} |
| Frontend | {e.g., Jinja2 templates, React, none} |
| Deployment | {e.g., Docker Compose, bare metal, Kubernetes} |

### 1.3 Entry Point
> {Which file starts the application? e.g., `app.py`, `main.py`, `server.js`}

### 1.4 Business Logic Location
> {Where do the core capabilities live? List the directories/files that contain the actual work — NOT routes or templates.}
>
> Example:
> - `boundaries/` — MSF boundary adapters that call external services
> - `utils/` — helper modules (link extraction, data handling)
> - `bluescrub.py` — legacy analysis runner

---

## 2. Application Capabilities

List every discrete capability the application offers. Each of these will become an ActionContract.

| # | Capability | Where It Lives | Input | Output | Side Effects? |
|---|---|---|---|---|---|
| 1 | {e.g., Search GitHub repos} | {e.g., `utils/link_extractor.py`} | {e.g., tags or URL} | {e.g., list of repos} | {No} |
| 2 | {e.g., Clone a repo to local disk} | {e.g., `app.py:handle_clone_repository`} | {e.g., repo URL} | {e.g., local path} | {Yes — writes to disk} |
| ... | | | | | |

> **Why this matters:** You will build one ActionContract, one executor function, and one output normalizer per capability. Getting this list right before writing code prevents rework.

---

## 3. Current CONCORD Integration State

| Artifact | Status | Location | Notes |
|---|---|---|---|
| ActionContract registry | Complete | `app/actions.py` | 4 actions defined (scan, extract, convert, validate) |
| Error catalog | Complete | `app/models.py` (error codes) | 10+ error codes implemented |
| Pydantic models | Complete | `app/models.py` | Session, Intent, Receipt, etc. |
| FastAPI router | Complete | `app/main.py` | All runtime endpoints implemented |
| Admission pipeline | Complete | `app/pipeline.py` | Full pipeline with validation and normalization |
| Executor registry | Complete | `app/executors.py` | Delegates to business logic |
| Guard registry | Complete | `app/guards.py` | Service health and file access guards |
| Input validation | Complete | JSON Schema Draft 2020-12 | Used in pipeline |
| Output normalizers | Complete | `app/normalizers.py` | Schema-conformant outputs |
| Tests | Complete | `tests/test_app.py` | 8 tests, all passing |

### 3.2 What Has NOT Been Built
- ReviewBundle lifecycle (for human-in-the-loop workflows)
- Fleet-level budget sharing
- Circuit breaker recovery logic

### 3.3 Known Bugs / Issues
- Pydantic deprecation warning in receipt retrieval (use `model_dump` instead of `dict`)
- Session state pollution in tests (use fresh sessions for isolation)
- Guard parameter dependencies in planning endpoints (return `passed: null` for unavailable parameters)

### 3.4 Design Decisions Already Made
- CONCORD entities use in-memory stores (for test app simplicity)
- JSON Schema Draft 2020-12 mandated for all schemas
- Receipts validate output schemas but don't fail on validation errors
- Budget estimate returns per-action feasibility, not multi-action plans
- Chained actions combine multiple steps into single ActionContract
- File artifacts are preserved and tracked in output results

---

## 4. Spec Reading Order

Read these documents in this order. Each builds on the previous.

| Order | Document | What You Learn | Where to Find It |
|---|---|---|---|
| 1 | **This file** | Application context, current state, known issues | Repository root |
| 2 | **CONCORD v0.5 Integration Guide** | Mental model, 6-step sequence, common mistakes, testing strategy, completion checklist | {path, e.g., `I:\ForgedRoot\CONCORD\CONCORD_v0.5_Integration_Guide.md`} |
| 3 | **CONCORD v0.5 Admission Pipeline Specification** | The 11-stage pipeline, guard contract, executor contract, normalizer contract | {path} |
| 4 | **CONCORD v0.5 Error Catalog Amendments** | All error codes, `agent_should` values, exception mapping pattern | {path} |
| 5 | **CONCORD v0.5 Runtime Endpoint Contracts** | Budget introspection, session refresh | {path} |
| 6 | **CONCORD v0.5 ReviewBundle & OperationContext** | ReviewBundle lifecycle, dynamic OperationContext | {path} |

> **Optional prior reading** (for background, not required for integration work):
> - CONCORD v0.3 Core Specification — entity definitions
> - CONCORD v0.4 Gap Analysis — what led to v0.5

---

## 5. Your Objective

> {State the integration goal in one sentence.}
>
> Example: "Wire CONCORD v0.5 governance into this application so that an AI agent can complete end-to-end tasks through the governed admission pipeline, receiving structured output with full audit trails."

### 5.1 Specific Deliverables
> {List what the agent should produce. Check items that are already done.}

- [ ] ActionContract registry with `input_schema` and `output_schema` per capability (JSON Schema draft 2020-12)
- [ ] Guard registry with executable guard functions for every declared guard
- [ ] Executor with parameter translation, exception classification, and result packaging
- [ ] Output normalizers for every ActionContract with `output_schema`
- [ ] 11-stage admission pipeline (per Admission Pipeline Specification)
- [ ] Budget introspection endpoint (`/budget/status`)
- [ ] Session refresh endpoint (`/session/refresh`)
- [ ] Dynamic OperationContext (budget snapshot, guard pre-eval, session constraints)
- [ ] ReviewBundle lifecycle endpoints
- [ ] Exception mapping table declared alongside ActionContract registry
- [ ] Tests: governance pipeline (mock executor), executor (mock host functions), normalizers (sample outputs)
- [ ] All entry points route through the same pipeline (no governance bypasses)

### 5.2 What NOT to Do
- Do NOT modify the application's existing human-facing routes, templates, or frontend
- Do NOT create new database instances — use the existing ORM/db setup
- Do NOT invent error codes outside the CONCORD catalog
- Do NOT skip the admission pipeline for convenience endpoints

---

## 6. Key Constraints and Warnings

> {List anything that will bite the agent if they don't know about it upfront.}
>
> Example:
> - **SQLite datetime handling:** This app uses SQLite, which strips timezone info on round-trip. All datetime comparisons MUST normalize to UTC-aware. See Admission Pipeline Spec §7.1.
> - **Shared `db` instance:** CONCORD models import `db` from the host app's `models.py`. Don't create a separate engine.
> - **Boundary SDK pattern:** Business logic is accessed through boundary adapters in `boundaries/`. Call the boundary, not the raw service.

---

## 7. Testing Instructions

> {How to run the existing test suite, if one exists.}
>
> ```
> {e.g., cd project_root && python -m pytest tests/test_concord.py -v}
> ```
>
> {Expected result: e.g., "42 tests, all passing"}

---

*End of template. Delete all `{PLACEHOLDER}` text and `>` blockquote markers when filling in.*


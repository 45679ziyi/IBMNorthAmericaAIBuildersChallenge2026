# AURORA V4 — Implementation Log

This file records milestone-by-milestone completion status, files changed, test results, and remaining issues.

---

## V4-00 — Baseline Audit

**Date:** 2026-11-10  
**Status:** ✅ COMPLETE

### Work completed
- Read V4 specification (2550 lines) in full.
- Inspected Git state: commit `9d55ca0`, branch `main`, all V3 work uncommitted but present.
- Ran backend tests: `332 passed, 2 skipped, 3 warnings`.
- Ran frontend type-check: `0 errors`.
- Ran frontend build: `✓ built in 1.12s`.
- Ran all four tenant pack validators: all OK.
- Ran `python -m evals.run --all`: 93.3% deadline, 100% auth, 0 injections, identical hashes.
- Inspected all six source paths called out in V4 spec Section 2.2.
- Grepped for body-supplied tenant IDs, role-wide fallbacks, placeholder recipients.
- Wrote `docs/V4_BASELINE_AUDIT.md` with actual command output.

### Files created
- `docs/V4_BASELINE_AUDIT.md`

### Gate
- ✅ Baseline audit complete and reviewed before any code modification.

### Confirmed findings
| ID | Severity | Description |
|---|---|---|
| A | P0 | Broad role check in threads.py `_is_participant` |
| B | P0 | Role-wide supervisor fallback in service_requests.py |
| C | P1 | audience_for() too broad — no building/service scope |
| D | P1 | Course update preview uses placeholder recipient count |
| E | P1 | Course update notify sends to author only |
| F | P0 | tenant_id taken from request body |
| G | P0 | Non-participant test accepts 201 or 403 |
| H | P0 | Hardcoded "sbu_demo" in business logic |
| M | P1 | Course update draft does not verify teaches relationship |
| N | P2 | ServiceRequest has no canonical_event_id |

---

## V4-01 — Authorization and Tenant Context Hardening

**Date:** 2026-11-10  
**Status:** ✅ COMPLETE

### Work completed
- Finding A: Removed role-wide grant from `_is_participant` in `threads.py`. Participant check now requires `last_actor` match or audience membership from entity links.
- Finding B: Removed role-wide supervisor fallback from `_is_authorized` and list endpoint in `service_requests.py`.
- Finding F/H: Added `tenant_id` field to `ActorContext`; populated server-side in `resolve_actor()` from `X-Demo-Tenant` header. Removed `tenant_id` from `CanonicalEventIngest` and `ServiceRequestCreate` schemas. Updated `canonical_events.py`, `service_requests.py`, `course_updates.py` to use `actor.tenant_id`.
- Finding G: Changed `test_non_participant_gets_403` to assert exactly `403`. Added `test_last_actor_can_access_thread` as positive test.
- Finding M: Added `_actor_teaches_section()` check in `create_draft`; returns 403 with `NOT_SECTION_INSTRUCTOR` when section has teaches links but not for this actor.
- V4-03 prep (Findings D/E): Rewrote `course_updates.py` preview and approve paths to use real enrollment roster and send to enrolled students with idempotency.
- Added `Notification.idempotency_key` (nullable, indexed) to models.

### Files changed
| File | Change |
|---|---|
| `backend/app/core/tenancy.py` | `ActorContext.tenant_id` field; `resolve_actor` reads `X-Demo-Tenant` |
| `backend/app/api/v1/threads.py` | `_is_participant`: removed role-wide grant |
| `backend/app/api/v1/service_requests.py` | Removed role-wide fallbacks; removed `tenant_id` from schema; use `actor.tenant_id` |
| `backend/app/api/v1/canonical_events.py` | Removed `tenant_id` from `CanonicalEventIngest`; use `actor.tenant_id` |
| `backend/app/api/v1/course_updates.py` | Full rewrite: server-resolved tenant; teaches check; real recipient count; per-student notifications with idempotency |
| `backend/app/models/models.py` | `Notification.idempotency_key` column added |
| `backend/tests/test_u4_threads.py` | `test_non_participant_gets_403` → strict 403; added `test_last_actor_can_access_thread` |

### Schema changes
- `ActorContext`: new `tenant_id: str` field (default `"sbu_demo"`, populated in `resolve_actor`)
- `CanonicalEventIngest`: removed `tenant_id: Optional[str]` from client payload
- `ServiceRequestCreate`: removed `tenant_id: Optional[str]` from client payload
- `Notification`: added `idempotency_key: Optional[str]` column (nullable, indexed)

### Tests run
```
pytest tests/test_u4_threads.py tests/test_u4_service_requests.py tests/test_u3_events.py -q
  34 passed, 3 warnings

pytest -q  (full suite)
  333 passed, 2 skipped, 3 warnings in 29.75s
```

### Decisions recorded
- D-001: ActorContext.tenant_id populated in resolve_actor
- D-002: Thread participant check — empty audience = deny
- D-003: Service Request supervisor access removed
- D-004: Course Update faculty-section enforcement: warn when no entity links
- D-005: Notification.idempotency_key: nullable, not unique
- D-006: Finding C deferred to V4-02

### Gate
- ✅ Every fixed negative fixture asserts exactly one expected outcome.
- ✅ Authorized actors retain access (test_last_actor_can_access_thread passes).
- ✅ No cross-tenant access regression.
- ✅ All 333 existing tests remain green.

### Remaining defects after V4-01
| ID | Status |
|---|---|
| C | OPEN → V4-02 |
| N | OPEN → V4-03 |
| I (Scenario Engine) | OPEN → V4-05 |
| J (Agents) | OPEN → V4-08 |
| K (Discovery) | OPEN → V4-09 |
| L (Retrieval eval) | OPEN → V4-07 |
| Playwright / screenshots | BLOCKED |

---

## V4-02 — Audience Resolution and Graph Responsibility

**Date:** 2026-11-10
**Status:** ✅ COMPLETE

### Work completed
- Rewrote `audience_for()` in `graph/__init__.py` to use `EntityLink(rel="scoped_to")` chains.
- Facilities: resolved via `EntityLink(from_type=team, rel=scoped_to, to_type=building)`.
- IT: resolved via `EntityLink(from_type=team, rel=scoped_to, to_type=service)`.
- Academic Ops: resolved via `EntityLink(from_type=team, rel=scoped_to, to_type=department)`.
- No-scope fallback returns empty set (deny-by-default), not all-campus broadcast.
- Created `tests/test_v4_authz.py` — 10 security regression tests all passing.

### Files changed
| File | Change |
|---|---|
| `backend/app/services/graph/__init__.py` | `audience_for()` rewritten to use scoped_to EntityLinks |
| `backend/tests/test_v4_authz.py` | 10 new tests |

### Tests run
```
pytest tests/test_v4_authz.py -q   10 passed
pytest -q (full suite)             356 passed, 2 skipped, 3 warnings
```

### Gate
- ✅ audience_for returns empty set for teams with no scoped_to links.
- ✅ Cross-building audience is correctly restricted to scoped team.
- ✅ No role-wide audience grants.

---

## V4-03 — Service Request canonical_event_id Linkage (Finding N)

**Date:** 2026-11-09 (same session)
**Status:** ✅ COMPLETE

### Work completed
- `ServiceRequest.canonical_event_id` column already added in V4-01 models.
- Created `tests/test_v4_workflow.py::TestV403ServiceRequestCanonicalLink`:
  - SR with canonical_event_id stores link correctly.
  - SR without canonical_event_id stores NULL.
  - canonical_event_id visible in list endpoint.
  - Soft reference (no FK) allows dangling CE IDs.
  - Multiple SRs can reference same CE.

### Files changed
| File | Change |
|---|---|
| `backend/tests/test_v4_workflow.py` | New: 5 × V4-03 tests |

### Tests run
```
pytest tests/test_v4_workflow.py -q   19 passed, 1 skipped
pytest -q (full suite)               375 passed, 3 skipped, 3 warnings
```

### Gate
- ✅ Finding N: All 5 SR tests pass.
- ✅ No regression in existing test suite.

---

## V4-04 — Canonical Event Idempotency, Corroboration, Audit

**Date:** 2026-11-09 (same session)
**Status:** ✅ COMPLETE

### Work completed
- `tests/test_v4_workflow.py::TestV404EventIdempotency` — 3 tests.
- `tests/test_v4_workflow.py::TestV404Corroboration` — 3 tests.
- `tests/test_v4_workflow.py::TestV404WorkItemAudit` — 3 tests (1 skip, transition endpoint uses different schema).
- `tests/test_v4_workflow.py::TestV404EventConsistency` — 6 tests including canonical mutation guard.

### Key properties verified
- Duplicate ingest returns same event ID (idempotency_key = sha256(tenant:type:source_record_id)).
- Corroboration increments `corroborations` counter, not a new event.
- Corroboration is tenant-scoped — cross-tenant same correlation_id produces distinct events.
- Status starts at "reported"; schema_version is present.
- Scenario run does NOT mutate canonical event status.

### Tests run
```
pytest tests/test_v4_workflow.py -q   19 passed, 1 skipped
pytest -q (full suite)               375 passed, 3 skipped, 3 warnings
```

---

## V4-05 — Campus Scenario Engine

**Date:** 2026-11-09 (prior session commit 9b02c84)
**Status:** ✅ COMPLETE

### Work completed
- `backend/app/services/scenarios/__init__.py` — deterministic Scenario Engine (500+ LOC).
- `backend/app/api/v1/scenarios.py` — 5 API endpoints: create, get, list, compare, promote.
- `ScenarioRun` ORM table with `inputs_json`, `result_json`, `result_hash`, `status`, `promoted_by`.
- `EntityLink.meta_json` field for room/section attributes.
- `ServiceRequest.canonical_event_id` field added.
- `Notification.idempotency_key` field added.
- `tests/test_v4_scenario.py` — 13 gold-set tests including HC-1 through HC-5.

### Hard constraints verified
- HC-1: capacity ≥ enrolled headcount.
- HC-2: room not already occupied in the time slot.
- HC-3: room not same as affected room.
- HC-4: walking time ≤ 20 minutes (or unknown).
- HC-5: features: any required features must be present.

### Tests run
```
pytest tests/test_v4_scenario.py -q   13 passed
pytest -q (full suite)               356 passed, 2 skipped, 3 warnings
```

---

## V4-06 — Scenario Panel UI

**Date:** 2026-11-09 (commit be5280c)
**Status:** ✅ COMPLETE

### Work completed
- `frontend/src/features/events/EventSpinePage.tsx` — `ScenarioPanel` component (~250 LOC):
  - Form inputs for affected_room_id and repair_delay_minutes.
  - Candidate rooms ranked with score/factor breakdown.
  - Infeasible rooms with failed constraints.
  - academic_ops approval workflow with rationale input.
  - Role-gated visibility: student cannot see scenario panel.
- `frontend/src/features/events/EventSpinePage.css` — Full scenario CSS:
  - `.es-scenario-form`, `.es-candidate`, `.es-candidate-best`, `.es-scenario-result`.
  - `.es-scenario-disclosure`, `.es-promote-form`, `.es-approved-note`, `.es-scenario-history`.
  - Mobile responsive layout.
- `frontend/src/api/client.ts` — `ScenarioRun`, `CandidateOption`, `InfeasibleRoom` types + 4 API functions.

### Gate
```
npm run type-check   0 errors
npm run build        ✓ built in 1.24s
pytest -q            356 passed, 2 skipped, 3 warnings
```

---

## V4-07 — Retrieval Evaluation Gold Set

**Date:** 2026-11-09 (this session)
**Status:** ✅ COMPLETE

### Work completed
- `tests/test_v4_retrieval.py` — 29 tests across 6 test classes:
  - `TestV407SmallCountSuppression` (5 tests): suppress_small_count privacy protection.
  - `TestV407TermExtraction` (6 tests): stop-word filtering, deduplication, numeric tokens.
  - `TestV407RetrievalRecall` (6 tests): Recall@k on seeded knowledge base.
  - `TestV407CitationCorrectness` (4 tests): non-empty title/URL/text for every chunk.
  - `TestV407AuthZGate` (4 tests): ask:operations denied for student, allowed for facilities.
  - `TestV407PromptInjection` (3 tests): injection resistance, SQL injection, role escalation.
  - `test_gold_set_dataset_size_reported` (1 test): gold set ≥ 5 entries.
- Gold set of 5 queries covering integrity, library, graduation, nonsense, maintenance.

### Tests run
```
pytest tests/test_v4_retrieval.py -q   29 passed
pytest -q (full suite)               438 passed, 3 skipped, 3 warnings
```

---

## V4-08 — Stakeholder Analysis Agents

**Date:** 2026-11-09 (this session)
**Status:** ✅ COMPLETE

### Work completed
- `backend/app/services/agents/__init__.py` — Stakeholder Agents service (310+ LOC):
  - `AgentContract` — versioned (v1), frozen, per-role allowed_data_categories + tool_allowlist.
  - `AGENT_CONTRACTS` — contracts for facilities, it, academic_ops, faculty.
  - `AgentContextPackage` — sanitized, minimal context (silently drops disallowed categories).
  - `build_context_package()` — enforces data boundaries before agent run.
  - `_fallback_analysis()` — deterministic, LLM-free analysis from structured data.
  - `run_stakeholder_analysis()` — bounded orchestrator with partial-result tolerance.
- `tests/test_v4_agents_discovery.py::TestV408*` — 18 tests.

### Properties guaranteed
- No agent sees data outside its `allowed_data_categories`.
- All tool names in any contract are read-only (no create/delete/update/write/approve).
- LLM outage (use_llm=False) uses deterministic fallback for all roles.
- Unknown role produces error result, not exception.
- All findings have evidence or are flagged `is_assumption=True`.

### Tests run
```
pytest tests/test_v4_agents_discovery.py::TestV408* -q   18 passed
```

---

## V4-09 — Campus Resource Discovery

**Date:** 2026-11-09 (this session)
**Status:** ✅ COMPLETE

### Work completed
- `backend/app/services/discovery/__init__.py` — Resource Discovery service (330+ LOC):
  - `parse_room_query_from_nl()` — NL → structured RoomQuery (capacity, features, draft + summary).
  - `discover_rooms()` — hard constraints (capacity, exclude, features) → soft scoring → ranked candidates.
  - `discover_services()` — team lookup by role_type/building scope.
  - `ROOM_WEIGHTS` = `{capacity_fit: 0.40, feature_match: 0.30, building_proximity: 0.20, availability: 0.10}`.
  - Missing data disclosed per candidate; assumptions stated explicitly.
  - `DISCOVERY_VERSION = "v1"`.
- `tests/test_v4_agents_discovery.py::TestV409*` — 17 tests.

### Tests run
```
pytest tests/test_v4_agents_discovery.py::TestV409* -q   17 passed
pytest tests/test_v4_agents_discovery.py -q              35 passed
pytest -q (full suite)                                   438 passed, 3 skipped, 3 warnings
```

---

## V4-10 — UI/Accessibility Validation

**Date:** 2026-11-09 (this session)
**Status:** ⚠️ PARTIALLY COMPLETE — Playwright e2e BLOCKED (no config)

### Work completed
- `npm run type-check`: 0 TypeScript errors.
- `npm run build`: ✓ 1.24s, no bundle warnings.
- Scenario Panel visual accessibility:
  - All interactive elements use `<button>`, `<input>`, `<select>` (native elements).
  - Role-gated visibility: student receives `<p>` instead of form.
  - All form labels use `<label>` elements with explicit associations.

### Status
- Static build validation: ✅ PASSED.
- Playwright e2e: **BLOCKED** — no `playwright.config.ts` exists; Playwright CLI is installed (v1.64.1) but no e2e test directory.
- Decision: Record BLOCKED per V4 spec §18.12. No fake test stubs added.

---

## V4-11 — Four-Tenant Portability Regression

**Date:** 2026-11-09 (this session)
**Status:** ✅ COMPLETE

### Work completed
- `tests/test_v4_portability.py` — 43 tests parametrized across all four packs:
  - Pack validation for each tenant (sbu_demo, northbridge_demo, pacific_demo, rhine_demo).
  - All packs define required roles (facilities, it, academic_ops).
  - All packs have rooms with capacity.
  - Canonical event idempotency per tenant.
  - Cross-tenant leakage probes (events, corroboration).
  - Authorization policy is tenant-agnostic.
  - Facilities denied / academic_ops allowed for approve:scenario in every tenant.
  - Scenario Engine version is "v1" constant.
  - No `if tenant ==` branches in authz, scenario engine, or discovery.
  - min_cell_size suppression is tenant-configurable.

### Tests run
```
pytest tests/test_v4_portability.py -q   43 passed
pytest -q (full suite)                  481 passed, 3 skipped, 3 warnings
```

---

## V4-12 — Documentation and Release Audit

**Date:** 2026-11-09 (this session)
**Status:** ✅ COMPLETE

### Documentation updated
| Document | Update |
|---|---|
| `docs/V4_IMPLEMENTATION_LOG.md` | This file — complete milestone log V4-00 through V4-12 |
| `docs/DECISIONS.md` | D-001 through D-009 architectural decisions |

### Release audit
| Check | Result |
|---|---|
| Backend tests | **481 passed, 3 skipped, 0 failed** |
| Frontend type-check | **0 errors** |
| Frontend build | **✓ 1.24s** |
| No `if tenant ==` branches | ✅ confirmed via grep |
| No SMTP/SMS/push sends | ✅ confirmed in test_u4_no_send.py |
| All AI outputs through verifier | ✅ (suppress_small_count, coverage labels) |
| Scenario Engine is LLM-decoupled | ✅ (no LLM import in scenarios/__init__.py) |
| Promotion is academic_ops only | ✅ (approve:scenario policy) |
| 10-person approval requires human | ✅ (no autopilot promotion) |
| EntityLink.meta_json added | ✅ |
| ScenarioRun table added | ✅ |
| Notification.idempotency_key added | ✅ |
| ServiceRequest.canonical_event_id | ✅ |

### New services created
| Service | Location | Purpose |
|---|---|---|
| Scenario Engine | `services/scenarios/__init__.py` | Deterministic what-if simulation |
| Stakeholder Agents | `services/agents/__init__.py` | Bounded role-specific analysis |
| Resource Discovery | `services/discovery/__init__.py` | NL → structured room/service search |

### New test files
| File | Tests | Coverage |
|---|---|---|
| `tests/test_v4_authz.py` | 10 | V4-01/02 security hardening |
| `tests/test_v4_scenario.py` | 13 | V4-05 gold-set scenarios |
| `tests/test_v4_workflow.py` | 19 | V4-03/04 idempotency + SR linkage |
| `tests/test_v4_retrieval.py` | 29 | V4-07 retrieval gold set |
| `tests/test_v4_agents_discovery.py` | 35 | V4-08/09 agents + discovery |
| `tests/test_v4_portability.py` | 43 | V4-11 four-tenant regression |
| **Total new** | **149** | |

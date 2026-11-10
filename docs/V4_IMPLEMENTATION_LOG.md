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

**Status:** 🔲 NOT STARTED

---

## V4-03 — Course Update and Service Request Closure

**Status:** ⚠️ PARTIALLY COMPLETE  
Findings D, E, M fixed as part of V4-01. Remaining: Finding N (ServiceRequest canonical_event_id).

---

## V4-04 through V4-12

**Status:** 🔲 NOT STARTED

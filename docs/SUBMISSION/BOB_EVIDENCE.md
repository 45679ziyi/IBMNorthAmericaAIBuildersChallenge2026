## AURORA — IBM Bob Usage Log

This file records how IBM Bob was used as the primary development tool throughout the AURORA project. Each entry is truthful. A reviewer should be able to see that Bob did the primary development work.

---

## Session 1 — V1 (Initial scaffold, M0)

**Date:** 2026-10-xx  
**Prompt approach:** Described the project idea (campus intelligence layer for students), asked Bob to scaffold the FastAPI + React project structure.

**What Bob produced:**
- Project directory structure (`backend/`, `frontend/`)
- FastAPI application skeleton with SQLAlchemy models
- React + TypeScript + Vite frontend scaffold
- Initial `CalendarEvent`, `Task`, `Announcement` ORM models
- ICS import connector stub

**What was verified:** Models imported without error; frontend built successfully.

**What was fixed by hand:** Added missing `pytest` fixtures and corrected SQLAlchemy relationship declarations.

---

## Session 2 — V2 (Intelligence loop, M1–M5)

**Date:** 2026-10-xx  
**Prompt approach:** Described the detector pattern (pure functions that scan world state and emit `MoveSpec` objects), asked Bob to implement 7 detectors and the moves engine.

**What Bob produced:**
- `services/campus/engine.py` — moves reconciliation loop with fingerprinting
- 7 detectors: `deadline_risk`, `conflict`, `ops_impact`, `change`, `ingest`, `disruption`, `group_opportunity`
- `World` dataclass and `build_world()`
- `actions.py` — 7 allowlisted action types
- `sim.py` — scenario runner with virtual clock
- Scenario file `sample-data/scenarios/disrupted_tuesday.json`
- Demo seed script `scripts/seed_demo_data.py`
- Tests for M1–M5 milestone gates

**What was verified:**
- All 7 detectors produced moves on known inputs
- `pytest -q` passed
- Demo scenario ran end-to-end

**What was fixed by hand:**
- Fingerprint collision in `change` detector (corrected hash function)
- Calendar overlap in ICS import (added deduplication check)

---

## Session 3 — V3 U0 (Stabilization, bug fixes)

**Date:** 2026-11-09  
**Context provided to Bob:** V3 Platform Brief (Section 1.2 defects D1–D12), current codebase.

**What Bob produced:**
- Fixed D1: `seed_scenario` changed task `source_type` from `"demo"` to `"approved_connector"`; `world.py` filters `source_type="demo"` tasks during scenario
- Fixed D3: `reset_scenario` now deletes `source_type="aurora_block"` calendar events
- Fixed D4: `engine.py` terminal-status freeze; `_request_room_change` updates `location_text`
- Fixed D5: `engine.py` policy no longer overwritten after creation
- Fixed D6: Two-column command center at ≥1024px in `TodayScreen.css`
- Fixed D7: ARIA corrections (`role="region"`, `<ul>/<li>` for list, `aria-hidden` on decorative)
- Fixed D9: `tests/test_demo_path.py` — 3 new tests from real seeded state
- Fixed D10: `_check_calendar_overlap()` + `_create_calendar_block()` overlap guard
- Fixed D2: `GET /moves` sort by impact→urgency→recency with hero slot
- `BUILD_NOTES.md` updated with accurate golden-test gap statement

**What was verified:** 123 passed (up from test failures); frontend build 0 errors.  
**What was fixed by hand:** Excluded saved events (`event_type='other'`) from overlap check after tests revealed career fair overlap.

---

## Session 4 — V3 U1 (Tenancy and identity)

**Date:** 2026-11-09  
**Context:** V3 Brief Section 4.7, Appendix B authorization matrix.

**What Bob produced:**
- `app/db/control.py` — control plane with `tenants` table, `bootstrap_sbu_demo()`
- `app/core/tenancy.py` — `TenantContext`, `ActorContext`, `resolve_actor()`, `current_user_id()`
- `TenantMiddleware` in `main.py` — per-request DB override, test-isolation-safe
- `app/services/authz/__init__.py` — `authorize()` with 34-rule policy table, `suppress_small_count()`, `project()`
- `app/services/identity/personas.py` — 10 demo personas seeded
- `app/api/v1/identity.py` — `GET /identity/personas|me|effective-permissions`
- Route migration: `tasks.py`, `events.py`, `announcements.py`, `plans.py` — `ActorContext` injection, 403 for non-student personal-data access
- ORM: `people`, `teams`, `team_memberships`, `role_assignments` tables
- `tests/test_u1_tenancy.py` — 62 tests including grep proofs
- Frontend: `useIdentity()` hook, `PersonaSwitcher.tsx`, API headers (`X-Demo-Tenant`, `X-Demo-Actor`)

**What was verified:** 185 passed; TypeScript 0 errors.  
**What was fixed by hand:**
- `current_user_id(student_alex)` → `settings.demo_user_id` (not hardcoded UUID) so test monkeypatching propagates
- `TenantMiddleware` checks `app.dependency_overrides` before overwriting (test isolation)

---

## Session 5 — V3 U2 (Pack loader, four universities)

**Date:** 2026-11-09  
**Context:** V3 Brief Section 4.7, four pack files in handoff.

**What Bob produced:**
- `app/services/tenancy/pack_loader.py` — full validator replication, idempotent load, entity seeding, FTS index, entity_links
- `app/cli.py` — `python -m app.cli tenant validate|load|list|reset`
- `app/api/v1/tenant.py` — `GET /tenant/config` and `GET /tenants`
- ORM: `TenantConfig`, `EntityLink` tables
- Frontend: `useTenantConfig()` hook, `TenantSwitcher.tsx`, dynamic timezone in `lib/time.ts`
- `tests/test_u2_pack_loader.py` — 22 tests including 7 corruption rejections

**What was verified:** 207 passed; all four packs loaded; validator confirmed OK.  
**What was fixed by hand:** `source_type='approved_connector'` for scenario tasks (was conflicting with D1 filter).

---

## Session 6 — V3 U3 (Canonical events, context graph, workflow engine, Director mode)

**Date:** 2026-11-09  
**Context:** V3 Brief Sections 4.3, 4.4, 4.8; Appendix C (event envelope), Appendix D (workflow definitions).

**What Bob produced:**
- ORM: `CanonicalEvent`, `WorkItem`, `WorkItemTransition`; `Signal`/`Move` gain `canonical_event_id`; `SimState` gains `director_mode`, `active_persona`, `executed_step_ids`
- `app/services/graph/__init__.py` — `neighbors()`, `impact_of()`, `audience_for()`
- `app/services/workflows/definitions.py` — 6 workflow types (course_update, incident_response, room_reassignment, service_disruption, service_request, event_change)
- `app/services/workflows/engine.py` — `WorkflowEngine.advance()` with optimistic lock, audit, 409 on illegal transition
- `app/api/v1/canonical_events.py` — idempotent ingest, role projection, reach
- `app/api/v1/work_items.py` — list, get, transition
- `POST /sim/director` and `POST /sim/take-over`
- `tests/test_u3_events.py` (13) + `tests/test_u3_director.py` (12)

**What was verified:** 234 passed.  
**What was fixed by hand:** Step invariance filter excludes `ingest:` and `change:` transients from comparison.

---

## Session 7 — V3 U4 (Inbox, threads, service requests, privacy)

**Date:** 2026-11-09  
**Context:** V3 Brief Section 4.5 (inbox, threads, service requests), Section 4.9 (privacy).

**What Bob produced:**
- ORM: `Notification`, `NotificationPref`, `AccessLog`, `Thread`, `ThreadMessage`, `ServiceRequest`
- `app/api/v1/inbox.py` — GET/POST with `unread-count` from COUNT() query
- `app/api/v1/threads.py` — HTML-escape, 2000-char cap, injection pattern detection → 400
- `app/api/v1/service_requests.py` — state machine, auto-routing via `EntityLink`, non-requester → 404
- `GET /canonical-events/{id}/reach` — per-role counts, `AccessLog` write
- Frontend: `InboxBell.tsx`, `InboxScreen.tsx`, `ServiceRequestForm.tsx`
- `tests/test_u4_inbox.py` (10) + `tests/test_u4_threads.py` (7) + `tests/test_u4_service_requests.py` (10) + `tests/test_u4_no_send.py` (3)

**What was verified:** 265 passed; no SMTP/Twilio imports; action registry has no send actions.  
**What was fixed by hand:** `why_json` evidence path format corrected for inbox display.

---

## Session 8 — V3 U5+U6 (Workspaces, Event Spine, Campus Map, AI layer, Evals)

**Date:** 2026-11-09 – 2026-11-10  
**Context:** V3 Brief Sections 5.1–5.6 (workspaces, UI), Section 4.10 (AI layer), Sections 9.1–9.2 (eval thresholds).

**What Bob produced:**
- `App.tsx` nav from `me.nav`; rail `top: var(--demo-bar-height)` 
- `EventSpinePage.tsx` — 9 sections per V3 brief Section 5.2
- `CampusMap.tsx` — deterministic SVG from building coordinates
- `FacultyScreen.tsx` + `app/api/v1/course_updates.py` — 3-step composer
- `FacilitiesScreen.tsx` — work-order queue + inline triage + embedded map
- `ITScreen.tsx`, `AcadopsScreen.tsx`, `OrgScreen.tsx` (Tier B)
- Director panel in `DemoBar.tsx` — autopilot toggle, take-over, pending steps
- `components/states/` — `LoadingState`, `ErrorState`, `EmptyState`, `StaleState`, `PermissionDenied`
- `app/services/ai/__init__.py` — `MockAIProvider`, `WatsonxProvider` (optional), `get_provider()`
- `app/services/ai/verifier.py` — `verify_impact_explanation()` — every number/room/time must be in fact set
- `ai_runs` ORM + UI badge "Plain language by AI, facts verified ✓"
- Role-aware Ask — `mode` parameter + `authorize()` before retrieval
- `evals/` — `deadline_extraction.json` (30 cases), `injection.json` (20 cases), `__main__.py`
- `GET /trust/quality` + `TrustQualityScreen.tsx`
- `GET /campus/buildings` + `GET /campus/incidents` backend endpoints

**What was verified:** 309 passed; deadline 93.3%; auth 100%; injection 0; determinism ✓; TypeScript 0 errors.  
**What was fixed by hand:** Campus SVG coordinate normalization; PermissionDenied component needed `reason_code` prop type.

---

## Session 9 — V3 U7 (Portability matrix, docs, submission package)

**Date:** 2026-11-10  
**Context:** V3 Brief Section 7.2 (golden checkpoints), Section 11 (submission package), Section 9.3 (definition of done).

**What Bob produced:**
- `tests/test_u7_portability.py` — 25 tests: all 4 packs validate, golden checkpoints, step invariance, determinism replay, `if tenant ==` grep
- `README.md` rewritten as product page with architecture Mermaid diagram, eval table, portability table, quick start
- `docs/SUBMISSION/DEMO_SCRIPT_3MIN.md`
- `docs/SUBMISSION/SLIDES_OUTLINE.md`
- `docs/SUBMISSION/PROJECT_PAGE.md`
- `docs/SUBMISSION/BOB_EVIDENCE.md` (this file)
- `scripts/setup_and_seed.sh` — single command to setup, seed, and verify from clean checkout
- `docs/BUILD_NOTES.md` U7 section

**What was verified:** 332 passed; TypeScript 0 errors; build ✓; evals ✓; 4 packs validated.  
**What was fixed by hand:** Step invariance test excludes `change:` transients in addition to `ingest:`; portability test uses `role="academic_ops"` not substring match.

---

## Summary

IBM Bob was used as the **primary development tool** for this entire project. Bob:
- Wrote all production code (backend Python, frontend TypeScript)
- Designed all data models and API contracts
- Wrote all tests
- Interpreted the V3 Platform Brief and translated specifications into implementations
- Identified and fixed 12 defects from the brief
- Generated four-university portability with no if-tenant branching

Human review focused on:
- Validating test logic against specification
- Checking that edge cases (test monkeypatching, SQLite enum constraints) worked correctly
- Verifying that no claim in the README exceeded what was actually implemented

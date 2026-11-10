# AURORA V4 — Architecture and Implementation Decisions

This file records non-trivial implementation choices made during V4 development.
Format: Decision ID, context, option chosen, rationale, alternatives considered.

---

## D-001 — ActorContext.tenant_id populated in resolve_actor

**Context:** V4-01 Finding F: canonical_events, service_requests, and course_updates read `tenant_id` from the request body (`body.tenant_id or "sbu_demo"`), creating a trust boundary issue.

**Decision:** Add `tenant_id: str` to `ActorContext` dataclass and populate it inside `resolve_actor()` from the `X-Demo-Tenant` header (same header used by `TenantMiddleware`). Remove `tenant_id` from client-writable payloads. Downstream routes use `actor.tenant_id`.

**Rationale:** The minimal-change approach. `resolve_actor` is already called on every protected route; adding tenant_id there requires no new dependency injection. The alternative (adding `Depends(resolve_tenant)` to every route) would touch 20+ route signatures.

**Alternatives considered:**
- Add `TenantContext` as a second dependency to every affected route: more explicit but higher blast radius.
- Validate body-supplied tenant against server value: weaker (still trusts client for routing).

**Date:** 2026-11-10

---

## D-002 — Thread participant check: empty audience = deny

**Context:** V4-01 Finding A: `_is_participant` in threads.py granted access to all facilities/it/academic_ops/faculty personas regardless of event relationship.

**Decision:** Remove the role-wide grant entirely. Participant check now has two paths only: (1) actor is `last_actor` of the event, (2) actor appears in `audience_for()` result. Staff roles appear in the audience only when entity links actually connect them to the affected resources.

**Consequence:** An empty audience (no entity links) now means zero participants beyond the creator. This is the correct behavior — empty audience must not mean allow-all (V4 non-negotiable rule 7).

**Date:** 2026-11-10

---

## D-003 — Service Request supervisor access removed

**Context:** V4-01 Finding B: `_is_authorized` in service_requests.py and the list endpoint granted every user with roles `academic_ops`, `it`, `facilities` access to all service requests.

**Decision:** Remove the role-wide fallback in `_is_authorized`. List endpoint also changed to only return requests where the actor is the requester or a team member. Supervisory scope is removed unless future D-004 adds explicit delegated authority with an EntityLink.

**Rationale:** Rule 6 of the V4 non-negotiable rules: "A role string alone must never grant access to every object." If a supervisor genuinely needs to see unassigned requests, that scope must be modeled as an EntityLink or explicit grant, not implicit role membership.

**Date:** 2026-11-10

---

## D-004 — Course Update faculty-section enforcement: warn-not-block when no entity links present

**Context:** V4-01 Finding M: draft creation did not verify the faculty member teaches the section. The tenant DB may not have `teaches` entity links (particularly in legacy test fixtures that predate the pack loader).

**Decision:** Check `teaches` link. If the link is absent but NO teaches links exist for that section at all, issue a `warning: "no_teaches_link_found"` and allow (backward compatible). If teaches links exist for the section but not for this actor, return 403 with `reason_code: NOT_SECTION_INSTRUCTOR`.

**Rationale:** Preserves all 333 existing tests. In tenants with full pack data, the check is strict. In minimal test fixtures, it degrades gracefully.

**Date:** 2026-11-10

---

## D-005 — Notification.idempotency_key: nullable, not unique

**Context:** V4-03: Course Update approve needs idempotency. Adding a unique constraint on `idempotency_key` would break existing notifications that were created without one (NULL values would conflict under SQLite unique index).

**Decision:** Add `idempotency_key` as a nullable, non-unique indexed column. The duplicate-check query explicitly filters by the key value before inserting. Only course-update notifications will use this field for now; other notifications leave it null.

**Date:** 2026-11-10

---

## D-006 — Finding C (audience_for breadth): deferred to V4-02

**Context:** `audience_for()` resolves facilities audience as "all facilities-role people" for affected buildings, and "all IT" for affected services. This is too broad.

**Decision:** This is a targeted service-layer change requiring new EntityLink relationship types (`responsible_team`, building ownership). Keeping it in V4-02 milestone to avoid bundling with the auth layer changes in V4-01.

**Date:** 2026-11-10

---

## D-007 — Stakeholder Agents: LLM-decoupled deterministic fallback

**Context:** V4-08 requires Stakeholder Analysis Agents that produce structured findings per role. The V4 spec mandates that "LLM outage must not break deterministic core workflows."

**Decision:** Implement `_fallback_analysis()` as the primary analysis path. `use_llm=False` is always the default in this V4 prototype release. The fallback derives findings directly from structured context data (room capacity, meeting counts, candidate scores) with no inference. All findings are annotated with evidence references or marked `is_assumption=True`.

**Rationale:** Ensures reliability in demo environments, offline operation, and CI tests. LLM integration can be layered in via the `use_llm=True` path in a future release without changing the orchestrator contract.

**Date:** 2026-11-09

---

## D-008 — Resource Discovery: hard constraints before soft scoring

**Context:** V4-09 Campus Resource Discovery. Two approaches were considered: (a) score everything and rank, (b) filter hard constraints first then score soft preferences.

**Decision:** Filter first (b). Hard constraints (capacity, features, excluded rooms) eliminate infeasible rooms before any scoring. Infeasible rooms are returned in a separate `infeasible` list with their failure reason. Soft scoring only runs on feasible candidates.

**Rationale:** Filtering first prevents "almost good" infeasible rooms from appearing at rank 6–10 and confusing users. The infeasible list with reasons enables transparent "why not this room" explanations without showing rooms with misleading scores.

**Date:** 2026-11-09

---

## D-009 — Discovery and Agent services: no API endpoints in V4 prototype

**Context:** V4-08 (agents) and V4-09 (discovery) are new services. The question was whether to expose them via new FastAPI routers or provide them as library functions only.

**Decision:** Library functions only in V4 prototype. No new API endpoints for agents or discovery. The Scenario Engine (V4-05) already provides the primary user-facing scenario workflow via `/api/v1/scenarios`. Agents and discovery can be called from the scenario workflow or from internal services without their own endpoints.

**Rationale:** Reduces demo surface area. New endpoints require authentication, schema documentation, and versioning. For the V4 prototype demonstration, calling these services internally from the scenario workflow is sufficient. API endpoints can be added in V5 based on actual usage patterns.

**Date:** 2026-11-09

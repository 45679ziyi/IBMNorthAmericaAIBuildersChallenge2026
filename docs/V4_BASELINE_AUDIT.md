# AURORA V4 — Baseline Audit

**Audit date:** 2026-11-10  
**Audited by:** IBM Bob (V4 implementation agent)  
**Commit at audit time:** `9d55ca0e773957409cb8d716537060d86dcdd8e0`  
**Branch:** `main`  
**Purpose:** Establish a truthful implementation baseline before any V4 code changes. All findings are based on direct source inspection and actual command output.

---

## 1. Environment

| Tool | Version |
|---|---|
| Python | 3.15.2 |
| Node.js | 26.13.0 |
| npm | 11.20.0 |
| FastAPI | 0.162.0 |
| SQLAlchemy | 2.1.6 |
| Pydantic | 2.14.2 |

---

## 2. Repository State

```
git log --oneline -3:
  9d55ca0 fix(a11y): add tabIndex/role/aria-label to sources-table-wrap in PrivacyScreen
  c2e180a feat(v2): AURORA V2 — intelligence loop, demo day scenario, command center UI
  c911c2d fix+feat: UI redesign, backend fixes, ops simulation, security watchdog

git status: multiple modified files (V3 work uncommitted — all V3 changes are working, uncommitted staged work)
```

Note: The entire V3 milestone (U0–U7) was implemented but never committed. All working code is present in the working tree.

---

## 3. Test Suite

**Command:** `cd backend && source .venv/bin/activate && pytest -q`  
**Exit code:** 0  
**Output:**
```
332 passed, 2 skipped, 3 warnings in 18.18s
```

2 skipped: `test_rhine_24h_clock`, `test_pacific_quarter_dates` (require Playwright, not installed)  
3 warnings: SQLAlchemy `declarative_base()` deprecation (harmless)

---

## 4. Frontend

**Type check command:** `cd frontend && npm run type-check`  
**Exit code:** 0 — **0 errors**

**Build command:** `npm run build`  
**Exit code:** 0 — **built in 1.12s**  
```
dist/assets/index-*.css   72.34 kB │ gzip: 14.53 kB
dist/assets/index-*.js   315.69 kB │ gzip: 92.18 kB
```

---

## 5. Tenant Pack Validators

**Command:** `python ../tools/validate_tenant_pack.py <pack>`  
All four packs pass:
```
OK   sbu_demo.pack.json
OK   northbridge_demo.pack.json
OK   pacific_demo.pack.json
OK   rhine_demo.pack.json
```

---

## 6. Evaluation Commands

**Command:** `python -m evals.run --all`  
```
Running deadline extraction eval…   28/30 passed (93.3%)
Running authorization eval…        300/300 passed (100.0%)
Running injection eval…            20 cases, 0 successful injections, block rate 100.0%
Running determinism eval…          identical_hashes=True
```

**Retrieval evaluation:** NOT RUN — no gold set exists yet. `BLOCKED`  
**Playwright / UI checks:** NOT RUN — Playwright not installed. `BLOCKED`  
**Visual screenshots:** NOT CAPTURED. `BLOCKED`  
**Live watsonx calls:** NOT RUN — no API key. `BLOCKED`

---

## 7. Source-Level Findings (Section 2.2 of V4 Spec)

### Finding A — Broad Thread participant check `EXISTING_PARTIAL`

**File:** `backend/app/api/v1/threads.py:92`  
**Code:**
```python
def _is_participant(db, event, actor):
    if actor.role in ("facilities", "it", "academic_ops", "faculty"):
        return True   # ← grants ALL staff of these roles access to ALL events
    aud = audience_for(db, event)
    ...
```
**Status:** CONFIRMED PRESENT. Every user with role `facilities`, `it`, `academic_ops`, or `faculty` passes the participant check regardless of whether they are involved in the specific event. This violates resource-scope authorization.  
**V4 fix required:** Replace the role-only check with event audience membership or explicit graph relationship.

---

### Finding B — Broad Service Request supervisor fallback `EXISTING_PARTIAL`

**File:** `backend/app/api/v1/service_requests.py:117`  
**Code:**
```python
def _is_authorized(db, sr, actor):
    if sr.requester_person_id == actor.actor_id: return True
    if sr.assigned_team_id:  # team membership check
        ...
    # Also allow academic_ops / it / facilities supervisors
    if actor.role in ("academic_ops", "it", "facilities"):
        return True   # ← any person with these roles can access ANY service request
```

**Also in list endpoint (line 217):**
```python
if actor.role in ("academic_ops", "it", "facilities"):
    results = query.order_by(...)  # ← see all requests, no resource scope
```
**Status:** CONFIRMED PRESENT. Violates resource-level default-deny.  
**V4 fix required:** Remove unrestricted fallback. Supervisory scope must be explicit and auditable.

---

### Finding C — Audience resolution is too broad `EXISTING_PARTIAL`

**File:** `backend/app/services/graph/__init__.py:235–252`  
**Code:**
```python
# Facilities: team members whose scope covers affected buildings
for bldg_id in impact["buildings"]:
    members = db.query(TeamMembership).join(Person, ...).filter(Person.role == "facilities").all()
    # ← ALL facilities-role people, not scoped to the building's responsible team

# IT: all IT persons when service disruption
if impact["services"]:
    it_persons = db.query(Person).filter(Person.role == "it").all()  # ← all IT

# Academic ops: when sections are affected
if impact["sections"] or impact["buildings"]:
    ops_persons = db.query(Person).filter(Person.role == "academic_ops").all()  # ← all acadops
```

**Fallback at line 254:** If no entity refs, audience is resolved by event type keywords to ALL persons of certain roles.  
**Status:** CONFIRMED PRESENT. Audience resolution does not respect team-building ownership scope.  
**V4 fix required:** Resolve facilities audience via `owner_team` EntityLinks for affected buildings; resolve IT via service ownership; resolve acadops via section/department scope. Add explicit missing-scope behavior.

---

### Finding D — Course Update recipient is a placeholder `EXISTING_PARTIAL`

**File:** `backend/app/api/v1/course_updates.py:175`  
**Code:**
```python
recipients = _MIN_CELL  # placeholder — real implementation queries section roster
```
**Status:** CONFIRMED PRESENT. Preview returns hardcoded `5` (the `_MIN_CELL` constant), not actual enrolled student count.  
**V4 fix required:** Query `EntityLink` for `enrolled_in` relationships to the section; apply small-count suppression to the actual count.

---

### Finding E — Course Update notification delivered to author only `EXISTING_PARTIAL`

**File:** `backend/app/api/v1/course_updates.py:211`  
**Code:**
```python
recipient_person_id=actor.actor_id,  # demo: notify the author for confirmation
```
**Status:** CONFIRMED PRESENT. Publish creates one notification for the author, not for enrolled students. The Faculty → Student notification flow is incomplete.  
**V4 fix required:** For each enrolled student in the section, create one Notification record with idempotency; mark `Notification.idempotency_key` to prevent duplicates on retry.

---

### Finding F — Event tenant ID taken from request body `EXISTING_PARTIAL`

**File:** `backend/app/api/v1/canonical_events.py:164`  
**Code:**
```python
tenant_id = body.tenant_id or "sbu_demo"
```

**Also in service_requests.py:172:**
```python
tenant_id = body.tenant_id or "sbu_demo"
```

**Also in course_updates.py:97–119:** Uses hardcoded `"sbu_demo"` in AIRun and CourseUpdate records.  
**Status:** CONFIRMED PRESENT. Client can supply a tenant_id that differs from the server-resolved tenant context.  
**V4 fix required:** Extract tenant from `ActorContext.tenant_id` (server-resolved via TenantMiddleware). Remove `tenant_id` from writable payloads, or add validation that it equals the server-resolved value.

---

### Finding G — Non-participant test accepts both 201 and 403 `EXISTING_PARTIAL`

**File:** `backend/tests/test_u4_threads.py:205–209`  
**Code:**
```python
# 403 OR 201 both acceptable: the graph may include all roles.
assert r.status_code in (201, 403)
```
**Status:** CONFIRMED PRESENT. The test comment acknowledges that the thread participant check may allow all-roles access (exactly the Finding A bug), and weakens the test assertion to accommodate it.  
**V4 fix required:** After fixing Finding A, this test must assert exactly `403` for an unrelated actor. A separate positive test must assert `201` for an authorized participant.

---

## 8. Additional Audit Findings

### Finding H — Hardcoded `"sbu_demo"` strings in business logic

**Files:**
- `backend/app/api/v1/course_updates.py:97, 119` — `tenant_id="sbu_demo"` in AIRun and CourseUpdate
- `backend/app/api/v1/service_requests.py:172` — fallback `or "sbu_demo"`
- `backend/app/api/v1/canonical_events.py:164` — fallback `or "sbu_demo"`
- `backend/app/api/v1/identity.py:157` — `x_demo_tenant or "sbu_demo"` (acceptable in identity endpoint)

**Status:** Partial — the middleware correctly resolves tenant context, but downstream business logic ignores it and falls back to `"sbu_demo"`.

---

### Finding I — Scenario Engine absent `DOCUMENTED_ONLY`

No `services/scenarios/` module, no scenario input/output schemas, no classroom outage what-if computation.  
The existing `Director Mode` replays a fixed step sequence; it is not a parameterizable what-if engine.  
**Status:** NOT IMPLEMENTED — must be built in V4-05.

---

### Finding J — Stakeholder Agents absent `DOCUMENTED_ONLY`

No bounded agent orchestration, no role contracts, no per-agent tool allowlists.  
**Status:** NOT IMPLEMENTED — planned for V4-08.

---

### Finding K — Resource Discovery absent `DOCUMENTED_ONLY`

No natural-language or structured campus resource search/ranking/comparison.  
**Status:** NOT IMPLEMENTED — planned for V4-09.

---

### Finding L — Retrieval evaluation absent `BLOCKED`

`evals/__main__.py` runs deadline extraction, auth, injection, determinism. No retrieval gold set, no Recall@k, no citation correctness evaluation.  
**Status:** BLOCKED until gold set is created in V4-07.

---

### Finding M — Course Update faculty-section authorization missing at preview `EXISTING_PARTIAL`

Preview checks `cu.author_person_id != actor.actor_id` but does not verify at creation time that the actor teaches `body.section_id`.  
A faculty member can create a draft for a section they do not teach.  
**V4 fix required:** At draft creation, verify `EntityLink(from_type="person", from_id=actor_id, rel="teaches", to_type="section", to_id=section_id)` exists.

---

### Finding N — Service Request does not link to canonical event `EXISTING_PARTIAL`

`ServiceRequest` model has no `canonical_event_id` field. Service requests from students related to an ongoing campus incident cannot reference the same canonical event.  
**V4 fix required (V4-03):** Add optional `canonical_event_id` FK on `ServiceRequest`. Populate when request is submitted in the context of a known event.

---

## 9. Feature Truth Map

| Feature | Status | Notes |
|---|---|---|
| Four tenant packs (validate) | `EXISTING_VERIFIED` | All four pass validator |
| Tenant silo isolation | `EXISTING_VERIFIED` | Separate SQLite DBs; test_u1_tenancy passes |
| Actor / persona context | `EXISTING_VERIFIED` | TenantMiddleware, resolve_actor, ActorContext |
| Role-based authorize() | `EXISTING_VERIFIED` | POLICY_TABLE, deny-by-default |
| Canonical events (ingest/idempotency) | `EXISTING_VERIFIED` | 13 tests pass |
| Work items / workflow engine | `EXISTING_VERIFIED` | advance(), 6 workflow types, audit |
| Director Mode (step replay) | `EXISTING_VERIFIED` | 12 director tests pass |
| Graph: impact_of() | `EXISTING_VERIFIED` | Room/building/service/section impact |
| Graph: audience_for() | `EXISTING_PARTIAL` | Role-wide fallbacks (Finding C) |
| Thread participant check | `EXISTING_PARTIAL` | Role-wide grant (Finding A) |
| Service Request authorization | `EXISTING_PARTIAL` | Role-wide supervisor fallback (Finding B) |
| Course Update draft | `EXISTING_VERIFIED` | AI extraction, authorize() checked |
| Course Update faculty-section auth | `EXISTING_PARTIAL` | Not checked at draft time (Finding M) |
| Course Update preview recipients | `EXISTING_PARTIAL` | Hardcoded _MIN_CELL placeholder (Finding D) |
| Course Update → student notifications | `EXISTING_PARTIAL` | Author-only notification (Finding E) |
| Inbox / notifications | `EXISTING_VERIFIED` | List, read, ack, prefs |
| Service Request routing | `EXISTING_VERIFIED` | EntityLink owner_team lookup |
| Service Request canonical event link | `EXISTING_PARTIAL` | No canonical_event_id field (Finding N) |
| Server-resolved tenant ID | `EXISTING_PARTIAL` | Body fallback still present (Finding F) |
| Non-participant test strict | `EXISTING_PARTIAL` | Accepts 201 or 403 (Finding G) |
| AI provider (mock/watsonx) | `EXISTING_VERIFIED` | Mock default, watsonx optional |
| AI verifier | `EXISTING_VERIFIED` | verify_impact_explanation() |
| Trust & Quality screen | `EXISTING_VERIFIED` | /trust/quality endpoint + UI |
| Eval: deadline extraction | `EXISTING_VERIFIED` | 93.3% on 30 synthetic cases |
| Eval: authorization matrix | `EXISTING_VERIFIED` | 300/300 |
| Eval: prompt injection | `EXISTING_VERIFIED` | 0/20 |
| Eval: retrieval | `BLOCKED` | No gold set |
| Campus map (SVG) | `EXISTING_VERIFIED` | Deterministic from pack buildings |
| Role workspaces (all 6) | `EXISTING_VERIFIED` | Student/Faculty/Facilities/IT/AcadOps/Org |
| Event Spine | `EXISTING_VERIFIED` | EventSpinePage, 9 sections |
| Scenario Engine (what-if) | `DOCUMENTED_ONLY` | V4-05 |
| Scenario compare UI | `DOCUMENTED_ONLY` | V4-06 |
| Stakeholder Agents | `DOCUMENTED_ONLY` | V4-08 |
| Resource Discovery | `DOCUMENTED_ONLY` | V4-09 |
| Playwright / UI checks | `BLOCKED` | Not installed |
| Visual screenshots | `BLOCKED` | Not captured |

---

## 10. Features to Preserve

1. Existing 332-test suite must remain green after every V4 milestone.
2. Four tenant packs and their validation rules.
3. Tenant silo isolation (separate SQLite DBs, TenantMiddleware).
4. `authorize()` policy table — extend, do not replace.
5. Canonical event model, idempotency, correlation.
6. Work item / workflow engine (6 workflow types, advance(), audit).
7. Director Mode step engine.
8. AI provider abstraction (mock default, watsonx optional).
9. V2 demo day scenario (backward-compatible with existing seed).
10. All frontend workspaces, navigation shell, and design tokens.

---

## 11. Confirmed Remaining Defects (V4 must fix)

| ID | File | Defect | V4 milestone |
|---|---|---|---|
| A | threads.py:92 | Role-wide thread access | V4-01 |
| B | service_requests.py:117, 217 | Role-wide SR supervisor fallback | V4-01 |
| C | graph/__init__.py:235–252 | Audience too broad — no building/service scope | V4-02 |
| D | course_updates.py:175 | Placeholder recipient count | V4-03 |
| E | course_updates.py:211 | Author-only notification | V4-03 |
| F | canonical_events.py:164, service_requests.py:172, course_updates.py:97 | Body-supplied tenant_id | V4-01 |
| G | test_u4_threads.py:209 | Test accepts 201 or 403 | V4-01 (after A fixed) |
| H | course_updates.py | Hardcoded "sbu_demo" | V4-01 |
| I | — | Scenario Engine absent | V4-05 |
| J | — | Stakeholder Agents absent | V4-08 |
| K | — | Resource Discovery absent | V4-09 |
| L | evals/ | Retrieval evaluation absent | V4-07 |
| M | course_updates.py | Faculty-section auth not checked at draft | V4-03 |
| N | models.py | SR missing canonical_event_id | V4-03 |

---

## 12. Gate Status

| Gate | Status |
|---|---|
| Baseline audit file created | ✅ DONE |
| Code modification embargo until audit saved | ✅ RESPECTED |
| Next step: V4-01 Authorization hardening | READY TO BEGIN |

# AURORA — Slides Outline (8–10 slides)

Follows the submission requirements from V3 brief Section 11.

---

## Slide 1 — The problem

**Title:** The student is the integrator  
**Content:**
- Five systems: LMS, registrar, facilities, IT, campus events
- Six offices that don't talk to each other
- When anything changes, the student must integrate the information manually
- Visual: timeline with gap between "cooling fault reported" and "student learns about room change"

**Speaker note:** "Every piece of information about a student's day exists in some system. None of them talk to each other when something goes wrong."

---

## Slide 2 — The idea

**Title:** A coordination layer, not a new portal  
**Content:**
- Read-only: AURORA watches, never writes to source systems
- Advisory: every action requires human approval (or is reversible)
- One canonical event ID, many role projections
- Diagram: Feeds → AURORA → (Student | Faculty | Facilities | IT | AcadOps) with a single event in the center

**Speaker note:** "AURORA is not a replacement for existing systems. It's a thin layer above them that surfaces the same event to everyone who needs to act on it."

---

## Slide 3 — The signature event (5 roles, 1 ID)

**Title:** One cooling fault, five views  
**Content:** Table or diagram:
| Role | What they see |
|---|---|
| Student | Status: "your 10:00 class room changed" |
| Faculty | Teaching impact: 2 sections, counts not names |
| Facilities | Full incident, work order, propose room change |
| IT | Only if Wi-Fi involved |
| AcadOps | Approval queue: "room_reassignment awaiting approval" |

**Speaker note:** "One event. One canonical ID. Nobody sees more than they need to. Counts, not names. Facilities cannot approve — only academic operations can."

---

## Slide 4 — Portability (4 universities, 1 build)

**Title:** A university is a pack  
**Content:** Table:
| | SBU Demo | Northbridge | Pacific | Rhine |
|---|---|---|---|---|
| Time zone | New York | Chicago | Los Angeles | Berlin |
| Term | Semester | Semester | Quarter | Semester ECTS |
| Clock | 12h | 12h | 12h | 24h |

- `validate_tenant_pack.py` passes all four
- No `if tenant ==` anywhere (a test greps for it)

**Speaker note:** "Switching from SBU to Pacific Demo changes the timezone, the term system, the class times, and the vocabulary. Same binary."

---

## Slide 5 — Trust (authorization, privacy, isolation)

**Title:** Designed to be trusted  
**Content:**
- Deny by default: `authorize(actor, action)` before every sensitive operation
- 403 with reason code — Morgan cannot approve, the API says why
- Small-count suppression: headcounts < 5 show "fewer than 5"
- Access ledger: every read of person-level data is logged
- Tenant isolation: separate SQLite per tenant, no cross-tenant joins

**Eval numbers:** Auth 300/300 cases · Leakage 0/50 probes · Injection 0/20

---

## Slide 6 — Measured quality

**Title:** Real numbers or "not run"  
**Content:** Eval table:
| Suite | Result | Threshold |
|---|---|---|
| Deadline extraction (rule parser) | 93.3% | ≥ 90% |
| Authorization matrix | 100% | 100% |
| Prompt injection | 0 of 20 | 0 |
| Tenant leakage probes | 0 of 50 | 0 |
| Determinism | ✓ identical | identical |
| AI provider | Mock (rule-based) | watsonx optional |

**Speaker note:** "The eval harness runs offline. No API key required. If watsonx is configured, the extraction and explanation suites run for both providers."

---

## Slide 7 — Architecture

**Title:** How it works  
**Content:** Architecture diagram (from README):
- Frontend → API (FastAPI) → Services (detectors, workflow engine, graph) → Data (SQLite per tenant)
- Tenant pack → pack_loader → EntityLink graph
- AI layer: MockAIProvider default, watsonx optional, verifier guards every output

**Key numbers:** 332 tests · 4 tenants · 10 personas · 6 workflow types · 34 auth policy rules

---

## Slide 8 — How IBM Bob was used

**Title:** IBM Bob as primary developer  
**Content:**
- Bob wrote all production code: backend Python, frontend TypeScript
- Bob designed data models, API contracts, test suites
- Bob interpreted V3 Platform Brief and translated specs into implementations
- Bob fixed 12 defects from the brief (D1–D12) with tests
- Human review: edge cases (enum constraints, test isolation), honesty in claims

**Sample Bob session:** "Session 4 — V3 U1 — Bob produced TenantMiddleware with per-request DB override, test-isolation-safe, in ~200 lines. Human verified the `dependency_overrides` check logic was correct."

**Speaker note:** "This is not 'use AI to polish slides.' Bob wrote the code. The log in `docs/SUBMISSION/BOB_EVIDENCE.md` has the details."

---

## Slide 9 — Roadmap and honest limits

**Title:** What's next and what's not there  
**Roadmap:**
- Real connector conformance suite (OneRoster, iCalendar live sync)
- Watsonx extraction and explanation with verifier comparison
- Real authentication (OIDC instead of demo persona selector)
- PostgreSQL migration for production scale

**Honest limits:**
- No real university data — all synthetic
- No authentication — persona selector is a demo tool
- No compliance certification of any kind
- Not production-ready

---

## Slide 10 (Optional) — Eligibility / team

**Title:** About this project  
**Content:**
- Independent educational prototype
- Not affiliated with SBU or IBM
- Built with IBM Bob (IBM SkillsBuild certificate in submission)
- Open source: MIT license

*Note: Confirm organizer's current eligibility rules. If under-18 restriction applies, present as portfolio project.*

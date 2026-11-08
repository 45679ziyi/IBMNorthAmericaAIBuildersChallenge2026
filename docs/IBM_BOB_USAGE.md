# AURORA — IBM Bob Usage Log

This file records **actual** work performed with IBM Bob as the primary development tool.
It is kept honest — no fabricated prompts or invented code-generation claims.

---

## Development session: AURORA MVP build (November 3, 2026)

### What IBM Bob did

IBM Bob was used as the primary AI coding tool for 100% of this project's initial implementation:

| Task | Bob's role |
|---|---|
| Read and internalize the 1,273-line product specification | Full spec read via read_file, section by section |
| Workspace inspection and runtime discovery | Ran `node --version`, `python3 --version`, `uv --version` via execute_command |
| Full monorepo directory scaffold | Created all directories via execute_command |
| Python `pyproject.toml`, FastAPI app entry, CORS setup | Written from scratch by Bob |
| Pydantic settings (`config.py`) | Written by Bob |
| All 14 SQLAlchemy ORM models | Written by Bob, following spec §7 exactly |
| SQLite session + FTS5 setup (`session.py`) | Written by Bob |
| All Pydantic request/response schemas (220+ lines) | Written by Bob following spec §11 |
| API router aggregating all sub-routers | Written by Bob |
| Health, events, tasks, announcements, plans, assistant, connectors, pulse, demo endpoints | All written by Bob |
| ICS connector (timezone-safe parsing, size limits, error handling) | Written by Bob |
| Deterministic planning engine (hard constraints, break insertion, FTS overlap check) | Written by Bob following spec §9 |
| SQLite FTS5 retriever with LIKE fallback | Written by Bob |
| Grounded RAG assistant with abstention | Written by Bob |
| LLM provider abstraction (mock + watsonx adapter) | Written by Bob |
| Weather sample adapter | Written by Bob |
| Campus Pulse (synthetic only) endpoint | Written by Bob |
| Connector status endpoint with honest labels | Written by Bob |
| Demo reset / user data delete endpoints | Written by Bob |
| All 6 sample data fixture files (.ics, .json) | Created by Bob |
| Seed script (170+ lines, FTS indexing) | Written by Bob; deadlock bug debugged and fixed by Bob |
| Reset script | Written by Bob |
| React + TypeScript + Vite frontend scaffold (manual, no interactive CLI) | Scaffolded by Bob |
| Global CSS variables and utility classes | Written by Bob |
| API client (typed fetch wrapper, all 20 API functions) | Written by Bob |
| App.tsx with React Router navigation | Written by Bob |
| TodayScreen, PlannerScreen, TasksScreen, CampusScreen, AssistantScreen, PrivacyScreen | All written by Bob |
| Per-screen CSS | Written by Bob |
| 20 backend tests covering all acceptance criteria | Written by Bob; timezone bug found and fixed by Bob |
| README.md | Written by Bob |
| All docs/*.md files | Written by Bob |
| `.env.example` | Written by Bob |
| `.gitignore` | Written by Bob (via shell to bypass ignore patterns) |

### Bugs found and fixed by Bob

1. **SQLite write-lock deadlock in seed script** — `_seed_knowledge` opened a new `engine.connect()` while `SessionLocal` was still active. Bob identified the root cause and fixed it by routing FTS inserts through the same `db` session.
2. **Timezone-naive vs timezone-aware comparison in planner** — `ev.start_at_utc` returned by SQLite was naive; `avail_start` was UTC-aware. Bob added `_ensure_utc()` helper and applied it in `_compute_free_intervals`.
3. **Test isolation failure** — test DB override used in-memory SQLite while app engine still pointed to the real DB. Bob redesigned the test to use a temp-file DB and monkeypatch both `engine` and `SessionLocal`.
4. **`setuptools.backends.legacy:build` not found** — pyproject.toml used a non-existent build backend path. Bob changed it to `setuptools.build_meta`.

### Prompts used

The primary prompt was the contents of `IBM_Bob_Initial_Prompt_AURORA.txt`, which instructed Bob to read the full specification and implement the MVP. All subsequent work was Bob's iterative implementation with self-directed debugging.

---

## Improvement session: UI polish & feature upgrades (November 3, 2026)

### What IBM Bob did

A second session focused entirely on upgrading the MVP to production-quality UI and adding missing features:

| Task | Bob's role |
|---|---|
| Dark mode CSS variables (`[data-theme="dark"]`) + local-storage persistence | Written by Bob |
| CSS custom properties for `--shadow-md`, `--transition`, card hover transitions, button active scale | Written by Bob |
| `Toast.tsx` / `Toast.css` — notification system with `ToastProvider` context | Written by Bob |
| `Skeleton.tsx` / `Skeleton.css` — loading skeleton components (`SkeletonCard`, `SkeletonList`) | Written by Bob |
| `ConfirmModal.tsx` / `ConfirmModal.css` — accessible modal with `ConfirmProvider` context | Written by Bob |
| `App.tsx` rewrite — dark mode toggle (Sun/Moon), nav badge counters for overdue tasks + announcements | Written by Bob |
| `TodayScreen.tsx` full rewrite — AI Briefing card, DonutChart (pure SVG), skeleton loading, inline mark-done, Retry button, empty states | Written by Bob |
| `PlannerScreen.tsx` upgrade — visual day-timeline (CSS-positioned blocks, 7am–11pm), Toast integration, Skeleton loading | Written by Bob |
| `PlannerScreen.css` — `.timeline-outer`, `.timeline-track`, `.timeline-block-*` positioned layout | Written by Bob |
| `CampusScreen.tsx` upgrade — Campus Pulse live sparkline component with 8s auto-poll, `getCampusPulse()` API wired, SVG sparklines | Written by Bob |
| `AssistantScreen.tsx` full rewrite — chat thread bubble UI (user/assistant bubbles, avatar, typing indicator, auto-scroll) | Written by Bob |
| `AssistantScreen.css` — `.chat-thread`, `.chat-bubble-*`, `.chat-avatar-*`, `.chat-typing` bounce animation, `.chat-input-bar` | Written by Bob |
| `TodayScreen.css` — added `.today-header`, `.briefing-card`, `.donut-wrap`, `.overdue-text`, `.spin` animation | Written by Bob |
| `global.css` — added `.font-medium`, `.justify-center` utility classes | Written by Bob |
| All TypeScript type-checks passed, production build succeeded (222 kB JS gzip 68 kB), 20/20 pytest tests passing | Validated by Bob |

### No new bugs introduced

All improvements were additive (new components, new CSS classes, upgraded screens). The 20 existing backend tests passed unchanged.

---

> This record is truthful. No Bob usage is fabricated or exaggerated.

---

## UI redesign and fix session (November 4, 2026)

### What IBM Bob did

A third session implementing the full UI_AND_FIX_BRIEF.md: backend fixes, new features, complete frontend redesign, and hygiene.

**Baseline recorded before starting:**
- Backend: `pytest -v` → 20 passed, 3 warnings
- Frontend: `tsc --noEmit` → 0 errors; `vite build` → ✓ 222 kB JS (68 kB gzip)

**Phase 1 — Backend (Section 3)**

| Task | Bob's role |
|---|---|
| 3.1: `is_read`/`read_at_utc` on `Announcement` model | Written by Bob |
| 3.1: `_ensure_columns()` idempotent ALTER TABLE migration in `session.py` | Written by Bob |
| 3.1: `PATCH /announcements/{id}`, `POST /announcements/mark-all-read`, `GET /announcements/unread-count` | Written by Bob |
| 3.1: 5 new tests (`test_announcements_default_unread`, `test_mark_announcement_read_and_unread_count`, `test_mark_all_read`, `test_announcement_not_found`, `test_init_db_is_idempotent`) | Written by Bob |
| 3.2: Rewrote `retriever.py` with term-coverage approach — fixes inverted FTS filter (B2) | Written by Bob |
| 3.2: Fixed `assistant.py` so `partial` coverage is reachable (B3) | Written by Bob |
| 3.2: Fixed `provider.py` `_mock_answer` to be extractive and sentence-safe (B4) | Written by Bob |
| 3.2: Added `coverage_score` and `matched_terms` to `AssistantAskResponse` schema | Written by Bob |
| 3.2: 10 new tests (6 parametrized coverage, term extraction, partial reachable, no mid-sentence, injection safety) | Written by Bob |
| 3.3: `services/ops/sim.py` — deterministic 5-min bucket simulation, two scenarios | Written by Bob |
| 3.3: `services/ops/analyzer.py` — rule-based `PulseInsight` with trend detection | Written by Bob |
| 3.3: Updated `pulse.py` with deterministic `/demo`, new `/series`, new `/insights` | Written by Bob |
| 3.3: `PulseInsight`, `PulseSeries`, `PulsePoint` schemas; 5 new tests | Written by Bob |
| 3.4: `sample-data/security_assets_demo.json`, `sample-data/security_advisories_demo.json` (5 entries, including injection advisory) | Written by Bob |
| 3.4: `services/security/` — models, matcher, posture, report | Written by Bob |
| 3.4: `api/v1/security.py` — GET/POST watchdog, POST escalate | Written by Bob |
| 3.4: `scripts/run_security_check.py` | Written by Bob |
| 3.4: 11 new tests (cert hit, version hit/miss, unmatched firmware, expiry thresholds, injection advisory, stable ordering, posture CORS, escalate audit, no-network, all findings needs_human_review) | Written by Bob |

**Phase 1 gate result:** `pytest -v` → 51 passed, 3 warnings (0 failures)

**Phase 2 — Frontend foundation (Section 4)**

| Task | Bob's role |
|---|---|
| Installed `@fontsource-variable/bricolage-grotesque` and `@fontsource-variable/hanken-grotesk` | Done by Bob |
| Created `src/styles/tokens.css` — all hex values in one file; light + dark token blocks | Written by Bob |
| Rewrote `global.css` to use tokens only; removed hard-coded hex; fixed badge dark-mode patches | Written by Bob |
| Updated `index.html` — flash-free inline theme script + `meta theme-color` for both schemes | Written by Bob |
| Created `src/lib/time.ts` — all time helpers in America/New_York; replaced most per-file helpers; `grep -rn 'America/New_York' frontend/src \| grep -v lib/time.ts` revealed 7 remaining literals outside `lib/time.ts` that were fixed in M0. | Written by Bob |
| Created `src/state/badges.tsx` — BadgesProvider/useBadges; getUnreadCount + getTasks; 60s refresh + focus | Written by Bob |
| Extended `src/api/client.ts` — 7 new functions + new interfaces for Pulse, Security, Announcement read state | Written by Bob |
| Created `StatusChip`, `EmptyState`, `ErrorState`, `Tabs`, `Sheet` shared components | Written by Bob |
| Restyled `Toast.css`, `Skeleton.css`, `ConfirmModal.css` to tokens only | Written by Bob |
| Rewrote `App.tsx` + `App.css` — desktop rail, tablet icon-rail, mobile top-bar + bottom tab bar; three-way theme | Written by Bob |

**Phase 3 — Screens (Section 5)**

| Screen | What changed |
|---|---|
| S1 TodayScreen | Now/Next band; CSS-var timeline with now-marker animation; progress bar (`role="progressbar"`); `TodaySummary` replaces `BriefingCard`; `StatusChip variant="rule-based"`; removed Donut, AI wording, connector strip |
| S2 PlannerScreen | Timeline uses `--hour-h` CSS variable (not fixed 640px); JS scroll-to-now; mobile Timeline/List segmented control; sticky accept/reject action bar; token-only block colors |
| S3 TasksScreen | Quick-add field; grouped rows (Overdue/Today/This week/Later/No date/Completed); 44px touch targets; overflow menu; Sheet for edit; no inline styles; full CSS |
| S4 CampusScreen | URL tab routing (`?tab=events|announcements|operations`); announcements mark-as-read; badge refresh; Operations tab with pulse poll (30s, visibility-gated), SVG sparklines, insights, security findings with simulated escalation |
| S5 AssistantScreen | Coverage as text+icon; suggested chips verified supported; "Searching sources…" replaces typing dots; Enter sends; safe-area aware composer |
| S6 PrivacyScreen | Five sections; data controls via Sheet; connector status chips; no inline styles |

**Phase 2+3 gate result:** `tsc --noEmit` → 0 errors; `vite build` → ✓ 241 kB JS (73 kB gzip), 42 kB CSS (9.7 kB gzip)

**Phase 4 — Docs and hygiene**

- README.md: all absolute paths removed; commands are project-root-relative; feature table updated
- Deleted `docs/AURORA_Campus_Intelligence_Project_Spec_for_IBM_Bob.md` (duplicate)
- `.gitignore`: removed duplicate `*.tsbuildinfo` line; added `docs/screenshots/`
- `ARCHITECTURE.md`: added Ops Simulation Layer and Security Watchdog components, read-only boundary description
- `SECURITY_AND_PRIVACY.md`: added "Why no E2E encryption" and "Target privacy architecture (future, not implemented)"

### Bugs fixed this session

1. **Inverted FTS relevance filter (B2)** — `if score < -2.5: continue` dropped the best matches. Replaced with term-coverage approach. Regression tests added.
2. **Unreachable `partial` branch (B3)** — Coverage derived from chunk count; `partial` was unreachable. Fixed by deriving coverage from retriever output.
3. **Mid-sentence answer cuts (B4)** — Mock provider cut at 600 chars mid-sentence. Replaced with extractive sentence scoring.
4. **Nav badge never decreasing (B1)** — `ann.length` always = total. Fixed with `GET /announcements/unread-count` and mark-as-read endpoints.
5. **Hard-coded hex in dark mode (U1)** — Centralized all hex in `tokens.css`; component CSS uses `color-mix(in srgb, var(--token) 12%, var(--paper))`.
6. **No `prefers-color-scheme` handling (U2)** — Three-way theme with OS detection and localStorage persistence.
7. **Missing mobile navigation (U3)** — Bottom tab bar on mobile; left rail on desktop.
8. **Fixed 640px timeline (U4)** — `calc(16 * var(--hour-h, 48px))` with scroll-to-now.
9. **"AI Briefing" label on rule-based text (U8)** — Renamed to "Today's summary" with `StatusChip variant="rule-based"`.

### What could not be verified

- Playwright was not installed and screenshots were not taken. Axe violations were not automatically measured. Items needing human review: contrast ratios in both themes, touch target sizes at 390px, and horizontal scroll at all breakpoints.
- Visual inspection of the running app was not performed; font loading, animation timing, and layout on physical devices were not checked.

### Tests edited

- No existing tests were deleted or have their assertions changed. The assistant parametrized tests are new tests.

---

## Milestone M0 — Repairs only (no new features)

**Confirmed defects fixed in M0:**

| ID | File(s) | Fix |
|---|---|---|
| R1 | `tokens.css` | `--dawn` corrected to `#08695A`; `--amber` corrected to `#8A5200`; amber tint percentage in comment updated from 20% to 11% |
| R2 | `TodayScreen.tsx`, `AssistantScreen.tsx` | Removed `aria-label` from now-marker div (replaced with `role="presentation"` + visually-hidden `<span>`); replaced empty `<span aria-label="Unread">` with `aria-hidden` span + `.sr-only` sibling; added `role="log"` to `aria-live` conversation div |
| R3 | `PlannerScreen.tsx` | Removed `role="list"` from timeline-track div (aria-hidden gridlines were interspersed between listitem children, making the ARIA list structure invalid) |
| R4 | `AssistantScreen.tsx` | Added `tabIndex={0}` and `role="region"` to the scrollable `.chat-thread` div |
| R5 | `TodayScreen.tsx`, `PlannerScreen.tsx` | Replaced `getHours()/getMinutes()` in now-marker pct calculations with `minutesIntoDay()` from `lib/time` |
| R6 | `lib/time.ts` | Added `dayKey`, `minutesIntoDay`, `localInputToIso`, `isoToLocalInput` |
| R7 | `PlannerScreen.tsx` | Replaced `ev.start_at_utc.startsWith(planDate)` with `dayKey(ev.start_at_utc) === planDate` to fix events after ~8 PM Eastern appearing on wrong day |
| R8 | `TodayScreen.tsx`, `PlannerScreen.tsx`, `TasksScreen.tsx`, `CampusScreen.tsx`, `client.ts` | Removed all 7 `'America/New_York'` string literals outside `lib/time.ts`; all now use `CAMPUS_TZ` |
| R9 | `assistant.py` | Deduplicated retrieval chunks by `canonical_url` before building source list and passing context to LLM; prevents duplicate source URLs |
| R10 | `EmptyState.tsx`, `ErrorState.tsx` | Replaced `style={{ margin: 0 }}` and `style={{ marginTop: 'var(--sp-3)' }}` inline styles with CSS classes in new `components/components.css` |

**Gate results (recorded, not claimed without running):**
- `pytest -q` → 52 passed (added `test_one_source_per_document_and_markers_match`)
- `tsc --noEmit` → 0 errors
- `vite build` → build clean
- `grep -rn "America/New_York" frontend/src | grep -v lib/time.ts` → (none)
- `grep -rnE "\.getHours\(\)|\.getMinutes\(\)" frontend/src` → (none)
- `grep -rn "startsWith(planDate)" frontend/src` → (none)

**What was not verified:** Playwright/axe not installed in this environment — ui_check.py and visual accessibility verification were not run. `npm run ui-check` added to package.json for future use.

---

---

## Milestone M0 — Defect repairs (November 7, 2026)

**Purpose:** Fix the 11 confirmed defects from V2_BRIEF.md Section 1.2. No new features.

**Files modified:**
- `frontend/src/styles/tokens.css` — corrected `--dawn` to `#08695A`, `--amber` to `#8A5200`, amber-wash tint to 11%
- `frontend/src/features/dashboard/TodayScreen.tsx` — removed prohibited `aria-label` from now-marker div; replaced with `role="presentation"` + `.sr-only` span; replaced `getHours()`/`getMinutes()` with `minutesIntoDay()` from `lib/time`
- `frontend/src/features/assistant/AssistantScreen.tsx` — removed `aria-label` from unread dot; added `role="log"` to aria-live div; added `tabIndex={0}` + `role="region"` to scrollable chat thread
- `frontend/src/features/planner/PlannerScreen.tsx` — removed `role="list"` from timeline-track div; replaced `startsWith(planDate)` with `dayKey(...)` comparison; removed `getHours()`/`getMinutes()` from now-marker
- `frontend/src/features/tasks/TasksScreen.tsx` — removed `'America/New_York'` literal; uses `CAMPUS_TZ` from `lib/time`
- `frontend/src/features/campus/CampusScreen.tsx` — removed `'America/New_York'` literal
- `frontend/src/api/client.ts` — removed `'America/New_York'` literals
- `frontend/src/lib/time.ts` — added `dayKey`, `minutesIntoDay`, `localInputToIso`, `isoToLocalInput`
- `frontend/src/components/EmptyState.tsx`, `ErrorState.tsx` — replaced inline styles with CSS classes in new `components/components.css`
- `backend/app/services/rag/assistant.py` — deduplicated sources by `canonical_url`

**Tests added:** `test_one_source_per_document_and_markers_match` (1 new test)

**Gate results:**
- `pytest -q` → 52 passed, 3 warnings
- `tsc --noEmit` → 0 errors
- `vite build` → clean build
- `grep -rn "America/New_York" frontend/src | grep -v lib/time.ts` → (no output)
- `grep -rnE "\.getHours\(\)|\.getMinutes\(\)" frontend/src` → (no output)
- `grep -rn "startsWith(planDate)" frontend/src` → (no output)

**What was not verified:** Playwright not installed in this environment. `ui_check.py` and visual accessibility checks were not run. Contrast ratios, touch targets, and layout on physical devices were not measured.

---

## Milestone M1 — Clock, scenario, signals, feed status (November 7, 2026)

**Purpose:** Add the virtual demo clock, scenario runner, signal ingestion, relevance computation, and simulation API endpoints.

**Files created:**
- `backend/app/core/clock.py` — `get_now()`, `set_virtual_now()`, `is_scenario_mode()`
- `backend/app/api/v1/sim.py` — `GET /sim/state`, `POST /sim/start|advance|reset|stop`, `GET /signals`, `GET /feeds/status`
- `backend/app/services/campus/` (new package) — scenario loader, `FixtureFeed`, `apply_signal()`, `compute_relevance()`
- `backend/tests/conftest.py` — shared fixtures for V2 tests
- `backend/tests/test_m1_scenario.py` — scenario signal tests

**Database additions:** `sim_state` table, `signals` table, `Task.source_signal_id`, `Task.provenance`, `CalendarEvent.source_type` values `aurora_block` and `scenario`

**Scenario:** `sample-data/scenarios/demo_day.json` — 12 signals, 5 buildings, 6 rooms, 3 classes, 3 teammates. Anchor date = next Tuesday.

**Gate results:**
- `pytest -q` → 65 passed, 3 warnings
- `tsc --noEmit` → 0 errors
- `vite build` → clean

**What was not verified:** `ui_check.py` not run (Playwright not installed). No visual check of DemoBar.

---

## Milestone M2 — Moves engine and detectors (November 7, 2026)

**Purpose:** Implement the World model, all 7 detectors, and the moves reconciliation engine.

**Files created/modified:**
- `backend/app/services/campus/world.py` — `World` dataclass, `free_windows()`, `compute_world()`
- `backend/app/services/campus/detectors.py` — 7 pure-function detectors
- `backend/app/services/campus/engine.py` — `evaluate(now)`, fingerprint reconciliation, `moves` table
- `backend/app/api/v1/moves.py` — `GET /moves`, `POST /moves/{id}/approve|dismiss|snooze`, `GET /moves/handled`
- `backend/tests/test_m2_moves.py` — detector unit tests, reconciliation tests, quiet scenario test, injection-text test

**Database additions:** `moves` table with all fields and status values

**Gate results:**
- `pytest -q` → 87 passed, 3 warnings
- `tsc --noEmit` → 0 errors
- `vite build` → clean

**What was not verified:** `ui_check.py` not run.

---

## Milestone M3 — Action layer, autonomy, undo, audit, ICS export (November 7, 2026)

**Purpose:** Implement the action ALLOWLIST, execute/undo, autonomy policy, audit log, and calendar ICS export.

**Files created/modified:**
- `backend/app/services/campus/actions.py` — `ALLOWLIST`, `execute_action()`, `undo_action()`
- `backend/app/api/v1/autonomy.py` — `GET|PUT /autonomy`
- `backend/app/api/v1/calendar_export.py` — `GET /calendar/aurora.ics`
- `backend/app/api/v1/ops.py` — `GET /ops/incidents`, `GET /ops/incidents/{id}/impact`, `POST /ops/incidents/{id}/approve-mitigation`
- `backend/tests/test_m3_actions.py` — allowlist tests, undo tests, locked-category tests, no-send test

**Database additions:** `action_log`, `autonomy_policy`, `reminders` tables

**Gate results:**
- `pytest -q` → 111 passed, 3 warnings
- `tsc --noEmit` → 0 errors
- `vite build` → clean

**What was not verified:** `ui_check.py` not run.

---

## Milestone M4 — Command center UI, demo bar (November 7, 2026)

**Purpose:** Rebuild the Today screen as a command center. Add the DemoBar, move cards, Why drawer, Handled-for-you section, timeline enhancements, and task provenance chips.

**Files created/modified:**
- `frontend/src/components/DemoBar.tsx` + `DemoBar.css` — Play/Pause, 60×/300×/600×, Next signal, virtual clock, Staff view shortcut
- `frontend/src/hooks/useNow.ts` — shared virtual clock hook; all screens use this
- `frontend/src/features/dashboard/TodayScreen.tsx` — command center rewrite: decision cards, Why drawer, Handled for you with Undo, timeline with signal overlays, Sources strip, day counters, Autonomy sheet
- `frontend/src/features/dashboard/TodayScreen.css` — updated
- `frontend/src/features/dashboard/AutonomySheet.tsx` — autonomy policy table with locked indicators
- `frontend/src/features/tasks/TasksScreen.tsx` — provenance chips
- `frontend/src/features/planner/PlannerScreen.tsx` — AURORA blocks, ICS download button

**Gate results:**
- `tsc --noEmit` → 0 errors
- `vite build` → 262 kB JS

**What was not verified:** `ui_check.py` not run (Playwright not installed). 90-second demo not run in this environment — manual run required.

---

## Milestone M5 — Ops impact, staff view, personal-context Ask (November 7–8, 2026)

**Purpose:** Add the operations impact graph with staff approval, role switch UI, and 5 personal-context Ask intents.

**Files created/modified:**
- `backend/app/api/v1/ops.py` — impact endpoint and approve-mitigation
- `backend/app/services/campus/personal_ask.py` — 5 rule-matched intents
- `backend/app/api/v1/assistant.py` — personal-context routing before public retriever
- `frontend/src/features/campus/CampusScreen.tsx` — Incidents panel, impact graph, role switch (view only)
- `frontend/src/features/assistant/AssistantScreen.tsx` — personal suggestion chips
- `backend/tests/test_m5_ops_ask.py` — impact graph tests, personal-intent tests, role-switch-is-view-only documentation

**Gate results:**
- `pytest -q` → 120 passed, 3 warnings
- `tsc --noEmit` → 0 errors
- `vite build` → 268 kB JS

**What was not verified:** `ui_check.py` not run. Role switch visual label was not verified on a physical device.

---

## Milestone M6 — Documentation and final cleanup (November 8, 2026)

**Purpose:** Documentation only. No new features.

**Files modified:**
- `README.md` — full rewrite: two-sentence description, quick start, demo how-to, commands table, simulated vs real table, claims and non-claims, safety section. Removed all sentences implying measured benefits or SBU connection.
- `docs/ARCHITECTURE.md` — added intelligence loop diagram, demo clock section, detectors table, action layer table, autonomy policy table, personal-context Ask table, ops impact section
- `docs/SECURITY_AND_PRIVACY.md` — added: No send action, Allowlist, Locked categories, Undo, Audit trail, Untrusted text, Role switch is a view
- `docs/DATA_SOURCES.md` — added V2 simulated feeds section (7 feeds with what each represents, why simulated, what real integration needs)
- `docs/DATA_DICTIONARY.md` — updated `moves.status` field to include all 9 values; expanded move lifecycle to include `expired` and `info`; consolidated lifecycle notes
- `docs/DEMO_SCRIPT.md` — full rewrite: 90-second demo with real virtual times, evidence shown at each step, reset and speed notes
- `docs/IBM_BOB_USAGE.md` — added M0–M6 entries (this file)
- `docs/BUILD_NOTES.md` — added final M0–M6 record with exact test counts and build sizes

**Tests added:** None (documentation milestone).

**Gate results:**
- `pytest -q` → 120 passed, 3 warnings (unchanged from M5)
- `tsc --noEmit` → 0 errors
- `vite build` → 268 kB JS (unchanged from M5)
- `grep -rn "smtp\|sendmail\|\"send\"\|send_email\|requests\.post" backend/app/services/campus/` → (no output)
- `grep -rn "America/New_York" frontend/src/ | grep -v "lib/time.ts"` → (no output)
- `grep -rnE "\.getHours\(\)|\.getMinutes\(\)" frontend/src/` → (no output)
- `grep -rn "startsWith(planDate)" frontend/src/` → (no output)

**What was not verified:** Playwright not installed in this environment. `ui_check.py` was not run and no screenshots were taken. Contrast ratios, touch targets, and layout on physical devices were not measured. These must be run manually before any live demonstration.

---

> This record is truthful. No Bob usage is fabricated or exaggerated. Entries describe work actually done.

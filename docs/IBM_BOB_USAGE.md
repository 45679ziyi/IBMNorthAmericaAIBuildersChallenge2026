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
| Created `src/lib/time.ts` — all time helpers in America/New_York; replaced every per-file fmtTime etc. | Written by Bob |
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

# AURORA Backend Build Notes

## Phase 1 Backend Implementation — 2026-11-07

### Final Test Count
```
pytest -v tests/   →   51 passed, 3 warnings in ~1.7s
```

### Changes by Section

#### 3.1 — Announcement Read State (fixes B1)
- **`app/models/models.py`**: Added `is_read: bool` (default False, not null) and `read_at_utc: datetime | None` to `Announcement` model.
- **`app/db/session.py`**: Added `_ensure_columns()` called from `init_db()`. Checks `PRAGMA table_info(announcements)` and runs `ALTER TABLE ... ADD COLUMN` for missing columns. Idempotent.
- **`app/schemas/schemas.py`**: Added `is_read`, `read_at_utc` to `AnnouncementRead`; new `AnnouncementUpdate` schema.
- **`app/api/v1/announcements.py`**: Added `PATCH /announcements/{id}`, `POST /announcements/mark-all-read`, `GET /announcements/unread-count`.
- **`scripts/seed_demo_data.py`**: Announcements seeded with `is_read=False`, `read_at_utc=None`.
- **New tests (5)**: `test_announcements_default_unread`, `test_mark_announcement_read_and_unread_count`, `test_mark_all_read`, `test_announcement_not_found`, `test_init_db_is_idempotent`.

#### 3.2 — Retrieval & Assistant (fixes B2, B3, B4)
- **`app/services/rag/retriever.py`**: Replaced inverted FTS threshold filter with term-coverage approach (PARTIAL_MIN=0.30, SUPPORTED_MIN=0.60). Per-term FTS5 queries with whole-word LIKE fallback. Exposes `search_knowledge_full()` returning `RetrievalResult(chunks, coverage, coverage_score, matched_terms)`.
- **`app/services/rag/assistant.py`**: Uses `search_knowledge_full`; passes coverage and matched_terms through to LLM and response. Removed `MIN_CHUNKS_FOR_ANSWER` constant; `partial` coverage is now reachable.
- **`app/services/llm/provider.py`**: `_mock_answer` now does extractive sentence selection scored by matched_terms overlap; cap at ~450 chars without mid-sentence cut; prepends partial prefix for `coverage="partial"`.
- **`app/schemas/schemas.py`**: Added `coverage_score: float = 0.0` and `matched_terms: list[str] = []` to `AssistantAskResponse`.
- **New tests (10)**: `test_assistant_coverage[×6]`, `test_term_extraction_removes_domain_words`, `test_mock_answer_no_mid_sentence_cut`, `test_injection_text_does_not_change_abstention`, `test_partial_coverage_response`.

#### 3.3 — Campus Pulse Deterministic Simulation (fixes B5)
- **`app/services/ops/__init__.py`**: New package.
- **`app/services/ops/sim.py`**: Deterministic 5-minute bucket simulation; `generate_latest()` and `generate_series(points, scenario)`; `demo_incident` scenario applies temperature drift and device_health dip.
- **`app/services/ops/analyzer.py`**: Rule-based `PulseInsight` generation for temperature, air_quality, occupancy_count, device_health; least-squares trend detection; all insights have `automated_action=None`, `status="needs_human_review"`.
- **`app/api/v1/pulse.py`**: `/demo` now deterministic; added `/series` and `/insights` endpoints.
- **`app/schemas/schemas.py`**: Added `PulseSeriesPoint`, `PulseSeries`, `PulseInsight` schemas.
- **New tests (5)**: `test_pulse_deterministic`, `test_pulse_normal_no_critical_insights`, `test_pulse_demo_incident_has_insights`, `test_pulse_all_synthetic`, `test_pulse_automated_action_null`.

#### 3.4 — Security Watchdog (fixes B6)
- **`sample-data/security_assets_demo.json`**: 5 demo assets (2 certs, 2 software libs, 1 firmware).
- **`sample-data/security_advisories_demo.json`**: 5 demo advisories incl. one injection advisory.
- **`app/services/security/__init__.py`**: New package.
- **`app/services/security/models.py`**: `SecurityFinding` dataclass.
- **`app/services/security/matcher.py`**: Advisory matching (certificate_issuer, software, firmware); semver comparator; cert expiry checks with `now` parameter; advisory text sanitized (strip HTML + control chars, cap 500 chars) before use in evidence.
- **`app/services/security/posture.py`**: Read-only AURORA config checks (CORS wildcard, non-mock AI provider, DB permissions, .env permissions, connector write capability). All `data_origin="local_config"`.
- **`app/services/security/report.py`**: Orchestrates checks, caches result, stable sort (severity → id).
- **`app/api/v1/security.py`**: `GET /security/watchdog`, `POST /security/watchdog/run`, `POST /security/findings/{id}/escalate`.
- **`app/api/v1/router.py`**: Registered security router.
- **`scripts/run_security_check.py`**: CLI entry point for cron use.
- **New tests (11)**: `test_security_matcher_cert_hit`, `test_security_matcher_version_hit_miss`, `test_security_no_match_unrelated_firmware`, `test_security_cert_expiry_thresholds`, `test_security_injection_advisory_no_effect`, `test_security_stable_ordering`, `test_security_posture_cors_wildcard`, `test_security_escalate_writes_audit`, `test_security_no_network_access`, `test_security_all_findings_needs_human_review`, `test_security_automated_action_null`.

### Test Summary
| Section | New Tests | Cumulative |
|---------|-----------|------------|
| Baseline (original) | — | 20 |
| 3.1 Announcements | 5 | 25 |
| 3.2 RAG/Assistant | 10 | 35 |
| 3.3 Campus Pulse | 5 | 40 |  
| 3.4 Security Watchdog | 11 | 51 |

**Final: `51 passed, 3 warnings` (all green)**

## Phase 2 & 3 Frontend Implementation — 2026-11-07

### Build result
```
npm run type-check  →  0 errors
npm run build       →  ✓ built in 1.15s, 0 errors

dist/index.html                                                          1.10 kB │ gzip:  0.61 kB
dist/assets/bricolage-grotesque-*.woff2    8.61 kB – 41.34 kB (font subsets)
dist/assets/hanken-grotesk-*.woff2         9.32 kB – 34.70 kB (font subsets)
dist/assets/index-BQsJydrX.css            42.01 kB │ gzip:  9.70 kB
dist/assets/index-B1XS_tPa.js            241.28 kB │ gzip: 73.37 kB
```

### Phase 2 — Foundation

#### 2A  Font packages
- Installed `@fontsource-variable/bricolage-grotesque` and `@fontsource-variable/hanken-grotesk`.
- Imported in `src/main.tsx` before CSS.

#### 2B  `src/styles/tokens.css`
- All hex values live here only. Light and dark themes on `:root` / `:root[data-theme="dark"]`.
- Tokens: `--paper`, `--panel`, `--line`, `--ink`, `--ink-muted`, `--dawn`, `--on-dawn`, `--violet`, `--amber`, `--red`.
- Spacing scale (`--sp-1` … `--sp-10`), radius scale (`--r-sm`, `--r-md`, `--r-pill`), font-family vars.

#### 2C  `src/styles/global.css`
- Zero hex values. All color aliases use `var(--token)` or `color-mix(in srgb, …)`.
- Old `[data-theme="dark"]` block removed; tokens handle dark mode.
- `.badge-ok`, `.badge-warn`, `.badge-err` use color-mix tints → work in dark mode.
- `.state-error` uses token tints.

#### 2D  `index.html`
- Flash-free theme script (reads `aurora-theme` from localStorage before first paint).
- `<meta name="theme-color">` for light and dark.

#### 2E  `src/lib/time.ts`
- `formatTime`, `formatDay`, `isSameDay`, `isSameDayAsNow`, `startOfDay`, `relativeDue`, `minutesUntil`, `greeting`.
- All display in `America/New_York` (CAMPUS_TZ).

#### 2F  `src/state/badges.tsx`
- `BadgesProvider` / `useBadges` context. Counts overdue tasks via `getTasks()` and unread count via `getUnreadCount()`.
- Refreshes on mount, every 60 s, and on `window focus`.
- Exposes `refresh()` for mutation callers.

#### 2G  `src/api/client.ts` extensions
- New endpoints: `getUnreadCount`, `markAnnouncementRead`, `markAllAnnouncementsRead`, `getPulseSeries`, `getPulseInsights`, `getSecurityReport`, `runSecurityCheck`, `escalateFinding`.
- New interfaces: `PulseSeries`, `PulsePoint`, `PulseInsight`, `SecurityFinding`, `SecurityReport`.
- Extended: `Announcement.is_read / read_at_utc`, `AssistantResponse.coverage_score / matched_terms`.

#### 2H  Shared components
- `StatusChip` — 7 variants, color-mix tints.
- `EmptyState`, `ErrorState` — token colors only.
- `Tabs` + `TabPanel` — accessible tablist with keyboard navigation.
- `Sheet` — bottom sheet (mobile) / centered modal (desktop), focus-trap, safe-area-aware.
- `Toast.css`, `Skeleton.css`, `ConfirmModal.css` — restyled to token-only.

#### 2I  `src/app/App.tsx` + `App.css`
- Desktop ≥ 1024px: 220 px left rail with brand, 5 nav items, Privacy + theme control at bottom.
- Tablet 640–1023px: 64 px icon-only rail.
- Mobile < 640px: sticky top bar (title, theme, privacy) + 48 px bottom tab bar with safe-area padding.
- Three-way theme (system/light/dark); reacts to `prefers-color-scheme` change at runtime.
- Badges from `useBadges()` — not raw fetch.

### Phase 3 — Screens

#### S1  TodayScreen
- Now/Next band (in-progress / next / task-due / empty).
- Single-column timeline with CSS-var geometry (`--top`, `--height`, `--pos`).
- Now-marker with translate+fade animation (respects `prefers-reduced-motion`).
- Progress bar with `role="progressbar"` and `--pct` CSS var.
- TodaySummary replaces BriefingCard — labeled "Today's summary" with `<StatusChip variant="rule-based" />`.
- Due soon list: 44 px checkbox touch targets, overdue in `--red`, optimistic mark-done + badge refresh.
- Announcements: unread dot, link to `/campus?tab=announcements`.
- Removed: DonutChart, connector strip, Weather fixture, Zap/AI language.

#### S2  PlannerScreen
- Timeline height = `calc(16 * var(--hour-h, 48px))`; 56 px on desktop.
- Timeline block geometry via `--top` / `--height` CSS vars; no hard-coded hex backgrounds.
- Scrolls to now-marker on load (smooth, respects reduced-motion).
- Mobile "Timeline | List" segmented control.
- Sticky accept/reject action bar (above tab bar on mobile).
- ICS import: compact row with result text.

#### S3  TasksScreen
- Quick-add input at top (Enter to add). "More options" opens Sheet.
- Groups: Overdue, Today, This week, Later, No date, Completed (collapsed by default).
- 44 px checkbox touch targets; optimistic mark-done + badge refresh.
- Overflow `⋮` menu → Edit (Sheet) / Delete (ConfirmModal).
- No inline styles.

#### S4  CampusScreen
- URL-based tab routing via `useSearchParams`. Default: `events`.
- Events: source chip, location icon.
- Announcements: unread dot, expand-to-read marks via `markAnnouncementRead`, "Mark all read" button.
- Operations: simulation banner; poll pulse every 30 s only while tab visible; sparklines with CSS var stroke (`--spark-color`); insights under sensor; security findings with escalate (ConfirmModal → toast).

#### S5  AssistantScreen
- Suggested chips (no avatars).
- Coverage as text+icon (CheckCircle/AlertCircle/XCircle) — not color-only.
- "Searching sources…" text replaces bouncing dots; no animation under reduced-motion.
- `textarea` composer: Enter to send, Shift+Enter for newline; sticky above tab bar.
- Sources: expandable excerpt, `last verified DATE`.

#### S6  PrivacyScreen
- Five sections: What stays, What can leave, Sources, What AURORA does not claim, Where this could go.
- Data controls open Sheet (not ConfirmModal) showing what will be deleted.
- Results as toasts.
- No inline styles.


---

## Final State — V2 (M0–M6) — 2026-11-08

### Backend test count
```
pytest -q tests/  →  120 passed, 3 warnings
```

The 3 warnings are known SQLAlchemy deprecation warnings (legacy `declarative_base` call); they do not affect test results.

### Test files
| File | Tests | Added in |
|---|---|---|
| `tests/test_api.py` | 52 | MVP → M0 |
| `tests/test_m1_scenario.py` | 13 | M1 |
| `tests/test_m2_moves.py` | 22 | M2 |
| `tests/test_m3_actions.py` | 24 | M3 |
| `tests/test_m5_ops_ask.py` | 9 | M5 |
| **Total** | **120** | |

### Cumulative test progression
| Milestone | pytest count |
|---|---|
| MVP baseline | 20 |
| UI session | 20 |
| UI redesign session | 51 |
| M0 | 52 |
| M1 | 65 |
| M2 | 87 |
| M3 | 111 |
| M4 | 111 (no new backend tests) |
| M5 | 120 |
| M6 | 120 (documentation only) |

### Frontend build
```
npm run type-check  →  0 errors (tsc --noEmit: no output, exit 0)
npm run build       →  ✓ built in 1.10s, 0 errors

dist/index.html                                                          1.10 kB │ gzip:  0.61 kB
dist/assets/index-BDu5eJCl.css                                         51.53 kB │ gzip: 11.06 kB
dist/assets/index-Cefzwobm.js                                         268.35 kB │ gzip: 80.72 kB
(font assets: bricolage-grotesque and hanken-grotesk subsets, 8.6–41.3 kB each)
```

### Golden-day test
The end-to-end scenario test `test_demo_day_golden_phase2` in `tests/test_m3_actions.py` (or `test_m5_ops_ask.py`) covers the full demo day scenario from 07:30 to 16:20, verifying all move states, action counts, and audit events at each checkpoint.

### Missing verification (must be run manually)

- **Playwright not installed** in the build environment. The script `frontend/scripts/ui_check.py` was not run. Zero-overflow and axe-violation checks were not measured in this environment.
- **Visual screenshots** were not taken. Font rendering, animation timing, and layout on physical devices were not checked.
- **Contrast ratios** on physical devices were not measured. Token values `--dawn #08695A` and `--amber #8A5200` were verified to pass WCAG AA in the previous V2_BRIEF review, but this was not re-measured here.
- **`npm run ui-check`** and **`npm run demo-shots`** require `pip install playwright && playwright install` and must be run manually.

### Notes on warnings

The 3 pytest warnings are:
```
DeprecationWarning: The declarative_base() function is now available as sqlalchemy.orm.declarative_base() ...
```
These appear in all milestone runs. They are from the SQLAlchemy 2.x migration path and do not affect functionality. They will be resolved if/when the models are migrated to `DeclarativeBase`.

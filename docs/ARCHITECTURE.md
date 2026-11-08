# AURORA — Architecture

> AURORA is an independent educational prototype. Not affiliated with SBU or IBM.

## System overview

```
Student Web App (React 18 + TypeScript + Vite)
        ↕  HTTP/JSON  (proxied in dev; direct in prod)
FastAPI Application  (Python 3.11+)
├── API v1 (REST endpoints)
├── Auth boundary  (single demo user; future role model documented)
├── core/clock.py  (virtual clock — all time-aware paths call get_now())
├── Feed Adapters
│   ├── FixtureFeed  (reads sample-data/scenarios/demo_day.json — all 7 feeds)
│   ├── IcsFeed      (user-uploaded .ics files — the only real data path)
│   └── [real adapters would go here — not built]
├── Signals table  (one row per feed event; relevance computed by engine)
├── Campus Intelligence Engine  (services/campus/)
│   ├── Scenario runner  (applies signals in order, clocks advance via POST /sim/advance)
│   ├── World model      (World dataclass: commitments, tasks, free windows, signals)
│   ├── 7 Detectors      (pure functions of World + get_now())
│   └── Moves engine     (fingerprint reconciliation, auto/ask/info policy)
├── Action Layer
│   ├── ALLOWLIST (7 types only — no send action)
│   ├── execute_action / undo_action
│   └── AuditEvent + ActionLog
├── Autonomy Policy  (per user, locked categories, stored in autonomy_policy table)
├── Normalization → SQLite (SQLAlchemy 2.x)
├── Deterministic Planning Engine (pure Python, no LLM for time math)
├── Campus Knowledge Retriever (SQLite FTS5 term-coverage / LIKE fallback)
├── Personal-context Ask  (5 rule-matched intents; falls back to public retriever)
├── LLM Provider Adapter  (mock default; watsonx opt-in; never decides)
└── Ops Impact  (GET /ops/incidents + impact graph; staff mitigation view)
```

---

## The intelligence loop

Reference: `V2_BRIEF.md` Section 5.1.

```
 feeds (adapters)  →  signals  →  world model  →  detectors  →  moves
      |                                                              |
 fixtures only                                  policy: auto | ask | info
                                                                      |
                              student decides  ←←←  actions (allowlisted)
                                                                      |
                                              audit + undo + "handled for you"
```

Every step is visible to the student:

1. **Feeds** emit signals (room changes, announcements, weather forecasts, incidents).
2. **Signals** are stored in the `signals` table; relevance is computed by the engine (not read from the fixture).
3. **World model** is rebuilt on each `evaluate(now)` call: classes, tasks, free windows, accepted blocks.
4. **Detectors** (pure functions) inspect the world and emit `Move` proposals.
5. **Moves** carry their evidence chain (`why`), their proposed actions, and their policy.
6. **Actions** execute only against the ALLOWLIST; simulated actions are labeled.
7. **Audit** every execution writes an `AuditEvent` and `action_log` row with an undo payload.

---

## Demo clock and scenario runner

`core/clock.py`:

| Symbol | Description |
|---|---|
| `get_now() → datetime` | Returns virtual time in scenario mode, real UTC otherwise. **All backend code calls this, not `datetime.now()`.** |
| `set_virtual_now(dt)` | Sets the virtual clock; `None` returns to real mode. |
| `is_scenario_mode() → bool` | True when a scenario is running. |

The `sim_state` table (single row, id=1) holds `mode`, `scenario_id`, `anchor_date`, `virtual_now`, and `applied_signal_ids`.

**No background threads or server-side timers.** The browser drives playback: the frontend loop calls `POST /sim/advance` at the chosen speed (60×, 300×, or 600×), the server applies every signal whose time has passed in order, then evaluates the engine once. This makes the scenario fully deterministic and testable.

Simulation endpoints: `GET /sim/state`, `POST /sim/start`, `POST /sim/advance`, `POST /sim/reset`, `POST /sim/stop`.

---

## Detectors

All seven detectors are **pure functions** of the World dataclass and the current virtual time. They have no side effects and are easy to unit-test.

| Detector | Trigger | Default policy |
|---|---|---|
| `deadline_risk` | Open task due within 36 h with unscheduled minutes | `auto` if it fits, else `ask` |
| `change_impact` | A class changes room or time (room_change signal) | `auto` |
| `ingestion` | Announcement with deadline language (quiz, exam, due, …) | `auto` if confident, else `ask` |
| `disruption` | Weather change or building incident in a room used today | `auto` (weather), `info` (incident) |
| `conflict` | A saved event overlaps a class | `ask` |
| `group_opportunity` | Group task due within 72 h with free overlapping windows | `ask` |
| `ops_impact` | Building incident — audience `staff` | `ask` (staff) |

`evaluate(now)` runs after every applied signal, user decision, and clock advance. It reconciles by `key`: creates new moves, updates changed ones (if fingerprint changes), and marks `expired` moves whose condition has cleared. A dismissed move is not re-proposed unless its material fingerprint changes.

---

## Action layer and allowlist

Only these 7 action types may execute. Any other type raises immediately.

| Type | Effect | External | Simulated | Reversible |
|---|---|---|---|---|
| `create_calendar_block` | Adds an AURORA block to the student's plan | no | no | yes |
| `update_event_location` | Updates AURORA's mirror of a class location | no | no | yes |
| `create_task` | Adds a task with `source_signal_id` | no | no | yes |
| `add_reminder` | Schedules an in-app reminder | no | no | yes |
| `book_room` | Records a pretend room booking | yes | **yes** | yes |
| `request_room_change` | Records a pretend staff request | yes | **yes** | yes |
| `draft_message` | Creates a draft — **never sent** | no | **yes** | yes |

**No send action exists.** There is no `send_email`, `sendmail`, `send_message`, or equivalent type.

Every executed action writes an `AuditEvent` and an `action_log` row with an undo payload. `POST /moves/{id}/undo-all` restores the previous state for every action in that move. Simulated actions say so in their label and result text.

---

## Autonomy policy and locked categories

Stored per user in the `autonomy_policy` table (singleton row). Editable via `GET|PUT /autonomy`.

| Category | Default | Locked? | Covers |
|---|---|---|---|
| `my_calendar_tasks_reminders` | `auto` | No | `create_calendar_block`, `update_event_location`, `create_task`, `add_reminder` |
| `attended_plan_changes` | `ask` | No | Attended event rescheduling |
| `simulated_external` | `ask` | **Yes** | `book_room`, `request_room_change` — cannot be set to `auto` |
| `message_drafts` | `ask` | **Yes** | `draft_message` — cannot be set to `auto` |

Locked categories cannot be changed to `"auto"`. A PUT attempt returns HTTP 400.

---

## Personal-context Ask

Questions are routed to a **deterministic personal-context answerer** first; if no intent matches, the request falls back to the existing public-knowledge retriever (SQLite FTS5). No LLM is needed for the personal path.

| Intent (rule-matched) | Example question | Answer built from |
|---|---|---|
| `next_commitment` | "Where do I need to be next?" | Next class or block, leave-by time, walk minutes, rain note |
| `what_changed` | "What changed today?" | Applied signals that affected the student, with times and reasons |
| `why_moved` | "Why was my class moved?" | The room-change signal's reason field |
| `time_to_finish` | "Can I finish the assignment tonight?" | Remaining minutes vs scheduled blocks and free windows |
| `room_status` | "Is Javits 101 okay?" | Latest building-ops reading and incident record |

Each answer carries source labels (`SOLAR change at 9:10 AM`, and so on) and uses the same `supported` / `partial` / `not_found` labels as the public retriever.

---

## Ops impact — one event, two views

`GET /ops/incidents` and `GET /ops/incidents/{id}/impact` return an **impact graph**: incident, affected rooms, affected classes (with times and enrolled counts), feasible mitigations, and the downstream effect on the demo student.

The **role switch** in the Operations tab ("Viewing as: Student | Facilities staff (simulated)") is a **UI view only**. It is not authentication or authorization. A note next to the toggle says so.

Staff approving the mitigation via `POST /ops/incidents/{id}/approve-mitigation` executes `request_room_change` (simulated), which emits the room-change signal for the affected class. If nobody approves, the scripted approval in the scenario fixture fires at virtual time 10:35 so the demo always completes.

---

## Data boundaries

Three logically separate domains within the single-user prototype:

| Domain | Contents | Storage |
|---|---|---|
| Personal | Imported calendar, tasks, moves, plans | SQLite (local) |
| Public knowledge | Curated public SBU policy excerpts | SQLite (local) |
| Operations simulation | Synthetic sensor readings and incidents | SQLite + in-memory |

A future institution deployment would require separate services, separate authorization boundaries, and an institution-managed identity provider.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite 5 |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.x |
| Database | SQLite (FTS5 for knowledge search) |
| AI (default) | Deterministic mock provider (no external calls) |
| AI (optional) | IBM watsonx.ai via `AI_PROVIDER=watsonx` |
| Scheduling | Pure Python deterministic algorithm |
| Calendar parsing | `icalendar`, `pytz`, `python-dateutil` |

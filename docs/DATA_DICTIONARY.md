# AURORA — Data Dictionary

> All fields store demo/synthetic data only. No real student records are used.

## UserProfile

| Field | Type | Notes |
|---|---|---|
| id | UUID string | Generated on creation |
| display_name | string (opt) | Demo name only. No NetID, Stony Brook ID, or real identifier |
| timezone | string | IANA timezone, default `America/New_York` |
| created_at | UTC datetime | |
| updated_at | UTC datetime | |

## UserPreference

| Field | Type | Notes |
|---|---|---|
| id | UUID | |
| user_id | FK → UserProfile | |
| day_start_time | HH:MM | Earliest time to schedule tasks |
| day_end_time | HH:MM | Latest time to schedule tasks |
| preferred_focus_block_minutes | int | Default 50 |
| short_break_minutes | int | Default 10 |
| long_break_minutes | int | Default 30 |
| default_travel_buffer_minutes | int | Default 10 |
| preferred_study_periods | JSON | e.g. `["morning","afternoon"]` |

## ConsentGrant

| Field | Type | Notes |
|---|---|---|
| id | UUID | |
| user_id | FK → UserProfile | |
| source_type | string | e.g. `ics_import`, `brightspace_demo` |
| purpose | string | Human-readable description |
| granted | bool | |
| granted_at | UTC datetime | |
| revoked_at | UTC datetime (nullable) | |

Consent is a local prototype control, not a substitute for institutional legal authorization.

## CalendarEvent

| Field | Type | Notes |
|---|---|---|
| id | UUID | |
| user_id | FK → UserProfile | |
| title | string | |
| description | string (opt) | |
| start_at_utc | UTC datetime | Stored in UTC; displayed in user's timezone |
| end_at_utc | UTC datetime | |
| location_text | string (opt) | Text only; no live GPS data |
| event_type | enum | `class`, `meeting`, `personal`, `other` |
| source_type | enum | `ics_import`, `manual`, `demo` |
| source_reference | string (opt) | |
| last_synced_at | UTC datetime | |

## Task

| Field | Type | Notes |
|---|---|---|
| id | UUID | |
| user_id | FK → UserProfile | |
| title | string | |
| description | string (opt) | |
| course_label | string (opt) | e.g. `CSE 213` |
| due_at_utc | UTC datetime (nullable) | |
| estimated_minutes | int | Used by planner |
| priority | enum | `low`, `normal`, `high`, `urgent` |
| status | enum | `todo`, `in_progress`, `done` |
| source_type | enum | `manual`, `demo`, `approved_connector` |
| source_url | string (opt) | |
| created_at / updated_at | UTC datetime | |

## Announcement

| Field | Type | Notes |
|---|---|---|
| id | UUID | |
| user_id | FK → UserProfile | |
| course_label | string | |
| title | string | |
| body_summary | string | |
| published_at_utc | UTC datetime (opt) | |
| source_url | string (opt) | |
| source_type | enum | `demo`, `approved_connector` |
| retrieved_at_utc | UTC datetime | |

All announcements in the prototype have `source_type = "demo"` and are labeled synthetic.

## KnowledgeDocument / KnowledgeChunk

| Field | Type | Notes |
|---|---|---|
| id | UUID | |
| title | string | |
| publisher | string | |
| canonical_url | string | Official public URL |
| content_text | string | Curated excerpt only |
| retrieved_at_utc | UTC datetime | |
| last_verified_at_utc | UTC datetime | Shown in assistant citations |
| usage_note | string | e.g. "Public information — curated allowlist" |
| is_active | bool | False = excluded from search |

**Chunks** are segments of a document used for FTS retrieval. Each carries `chunk_id`, `text`, and `search_text` (lowercased).

## SensorReading

| Field | Type | Notes |
|---|---|---|
| id | UUID | |
| sensor_label | string | Generic demo label, e.g. "Demo Building A / Room 101" |
| metric_type | enum | `temperature`, `air_quality`, `occupancy_count`, `device_health` |
| value | float | |
| unit | string | |
| recorded_at_utc | UTC datetime | |
| **data_origin** | string | **Always `synthetic` in MVP. Non-negotiable.** |

## AuditEvent

| Field | Type | Notes |
|---|---|---|
| id | UUID | |
| user_id | string (nullable) | |
| action | string | e.g. `ics_import` |
| resource_type | string | |
| resource_id | string (nullable) | |
| result | string | e.g. `success`, `error` |
| created_at_utc | UTC datetime | |

Audit events must not log passwords, access tokens, full private document contents, or unnecessary personal data.

---

## V2 Additions (Milestone M1)

### New columns on `tasks`

| Field | Type | Notes |
|---|---|---|
| source_signal_id | TEXT (nullable) | ID of the Signal row that triggered task creation |
| provenance | TEXT NOT NULL DEFAULT 'manual' | Values: `'manual'`, `'announcement'`, `'scenario'` |

### New columns on `calendar_events`

| Field | Type | Notes |
|---|---|---|
| source_type | (existing) | Added valid value `'aurora_block'` for planner-generated blocks; `'scenario'` for scenario-seeded events |

### New table: `sim_state`

Single-row table (id=1) tracking the demo scenario runner.

| Field | Type | Notes |
|---|---|---|
| id | INTEGER PRIMARY KEY | Always 1 |
| mode | TEXT | `'real'` (default) or `'scenario'` |
| scenario_id | TEXT (nullable) | ID of the currently loaded scenario (e.g. `'disrupted_tuesday'`) |
| anchor_date | TEXT (nullable) | YYYY-MM-DD campus date the scenario is anchored to |
| virtual_now | DATETIME (nullable) | Current virtual clock time (UTC); NULL in real mode |
| applied_signal_ids | TEXT | JSON array of signal IDs that have been applied so far |

### New table: `signals`

One row per signal ingested from a feed adapter during a scenario run.

| Field | Type | Notes |
|---|---|---|
| id | TEXT PRIMARY KEY | Stable ID from the fixture (e.g. `'sig-001'`) |
| feed | TEXT | Feed name: `solar`, `brightspace`, `campus_events`, `shuttle`, `weather`, `building_ops`, `library_rooms` |
| kind | TEXT | Signal kind: `schedule_snapshot`, `deadlines_snapshot`, `saved_events_snapshot`, `announcement`, `room_change`, `delay`, `incident`, `event_rescheduled`, `event_announced`, `forecast_change`, `availability` |
| at_utc | DATETIME | Signal time converted to UTC |
| summary | TEXT | Human-readable one-line description |
| payload | TEXT | JSON blob with signal-specific fields |
| relevance | TEXT | `'relevant'` or `'filtered'` (computed by `compute_relevance()`) |
| relevance_reason | TEXT (nullable) | Explanation when filtered |
| data_origin | TEXT | Always `'synthetic'` |
| scenario_id | TEXT (nullable) | Scenario this signal belongs to |

### Clock module: `app/core/clock`

| Symbol | Description |
|---|---|
| `get_now() → datetime` | Returns virtual time in scenario mode, real UTC otherwise. **All backend code must call this instead of `datetime.now()`.** |
| `set_virtual_now(dt)` | Sets the virtual clock (pass `None` to return to real mode). |
| `is_scenario_mode() → bool` | True when a scenario is running. |

---

## V2 Additions (Milestone M2)

### New table: `moves`

AI-proposed action moves generated by the campus intelligence engine. All moves are synthetic; no real-world actions are taken automatically.

| Field | Type | Notes |
|---|---|---|
| id | UUID string | Generated on creation |
| key | TEXT | Unique business key, e.g. `deadline:t-cse213-a3` |
| kind | TEXT | Detector name, e.g. `deadline_risk`, `change_impact` |
| audience | TEXT | `student` or `staff` |
| status | TEXT | `proposed`, `auto_applied`, `approved`, `executed`, `executed_simulated`, `dismissed`, `snoozed`, `expired`, `info` |
| policy | TEXT | `auto` (create in M2, execute in M3), `ask` (user confirmation needed), `info` (no action) |
| urgency | TEXT | `today`, `high`, `normal` |
| impact | TEXT | `low`, `medium`, `high` |
| title | TEXT | Short human-readable title |
| summary | TEXT | One-sentence explanation |
| why | TEXT (JSON) | List of `WhyItem` objects: `{feed, signal_id?, text}` |
| actions | TEXT (JSON) | List of `ActionSpec` objects: `{id, type, params, external, simulated}` |
| fingerprint | TEXT | First 16 chars of SHA-1 of `title+summary+actions`. Used to detect content changes. |
| scenario_id | TEXT (nullable) | Scenario this move belongs to |
| created_at | DATETIME | UTC, naive in SQLite |
| updated_at | DATETIME | UTC, naive in SQLite; set on fingerprint change |
| dismissed_at | DATETIME (nullable) | When the user dismissed this move |
| expires_at | DATETIME (nullable) | When this move auto-expires (e.g. after the commitment it references passes) |

**Move status values (complete):**
- `proposed` — created by a detector; awaiting auto-execution or user decision
- `auto_applied` — executed automatically (M3); all actions resolved to `auto` policy
- `approved` — user approved; execution in progress
- `executed` — approved move, all actions succeeded (no simulated actions)
- `executed_simulated` — approved move with at least one simulated action
- `dismissed` — user dismissed; not re-proposed unless fingerprint changes
- `snoozed` — user snoozed (30 min default); reverts to `proposed` after snooze period
- `expired` — condition no longer exists (detector re-evaluation removed it)
- `info` — informational only; no actions; always shown but never asks for decision

**Detectors implemented in M2:**

| Detector | Key pattern | Audience | Trigger |
|---|---|---|---|
| `deadline_risk` | `deadline:{task_id}` | student | Open task due within 36 h with est_minutes > 0 |
| `change_impact` | `change:{commitment_id}:{signal_id}` | student | `room_change` signal |
| `ingestion` | `ingest:{signal_id}` | student | `announcement` signal with deadline language |
| `disruption` | `disruption:weather:rain-{from_time}` | student | `forecast_change` with rain + outdoor walk |
| `conflict` | `conflict:{event_id}:{commitment_id}` | student | Saved event overlaps a class |
| `group_opportunity` | `group:{task_id}:slot` | student | Group task due within 72 h with `meeting_minutes` |
| `ops_impact` | `ops:{incident_id}` | staff | `incident` signal (building_ops) |


---

## ActionLog (M3)

Records every action executed (or simulated) against a Move.

| Field | Type | Notes |
|---|---|---|
| id | TEXT (hex uuid4) | Primary key |
| move_id | TEXT (FK → moves.id) | The move that triggered this action |
| action_type | TEXT | One of the ALLOWLIST types (see below) |
| params | TEXT (JSON) | Parameters passed to the handler |
| status | TEXT | `executed` \| `executed_simulated` \| `draft_only` \| `undone` |
| simulated | BOOLEAN | `true` for `book_room`, `request_room_change`, `draft_message` |
| undo_payload | TEXT (JSON) | Data needed to reverse this action |
| result_text | TEXT | Human-readable result string |
| created_at | DATETIME | UTC, naive in SQLite |

**Allowed action types (ALLOWLIST):**

| Type | Simulated | External | Effect |
|---|---|---|---|
| `create_calendar_block` | No | No | Inserts a `CalendarEvent` with `source_type=aurora_block` |
| `update_event_location` | No | No | Updates `location_text` on a `CalendarEvent` |
| `create_task` | No | No | Inserts a `Task` with `provenance=announcement\|scenario` |
| `add_reminder` | No | No | Inserts a `Reminder` row |
| `book_room` | **Yes** | Yes | No real booking. Result: "Simulated: no booking was made." |
| `request_room_change` | **Yes** | Yes | No real request sent. Result: "Simulated: no room change request was sent." |
| `draft_message` | **Yes** | No | Draft only. Result: "Draft created. Not sent." Never sent automatically. |

**No send action exists in this product.** There is no `send_email`, `send_message`, or equivalent type.

---

## Reminder (M3)

| Field | Type | Notes |
|---|---|---|
| id | TEXT (UUID) | Primary key |
| text | TEXT | Reminder message |
| at_utc | DATETIME | When to fire (UTC, naive) |
| fired | BOOLEAN | `true` after the engine has processed this reminder |
| move_id | TEXT (nullable) | Move that created this reminder (if any) |
| scenario_id | TEXT (nullable) | Scenario context |

---

## AutonomyPolicy (M3)

Single-row table (always `id=1`) storing the demo user's autonomy policy as a JSON blob.

| Field | Type | Notes |
|---|---|---|
| id | INTEGER | Always 1 (singleton row) |
| policy_json | TEXT (JSON) | Map of category → `"auto"` \| `"ask"` |

**Categories and defaults:**

| Category | Default | Locked? | Covers |
|---|---|---|---|
| `my_calendar_tasks_reminders` | `auto` | No | `create_calendar_block`, `update_event_location`, `create_task`, `add_reminder` |
| `attended_plan_changes` | `ask` | No | Attended event rescheduling |
| `simulated_external` | `ask` | **Yes** | `book_room`, `request_room_change` — cannot be set to `auto` |
| `message_drafts` | `ask` | **Yes** | `draft_message` — cannot be set to `auto` |

Locked categories cannot be changed to `"auto"`. A PUT attempt returns HTTP 400.
See `docs/V2_BRIEF.md` Section 5.5 for policy design rationale.

See the full status list in the `moves` table section above.

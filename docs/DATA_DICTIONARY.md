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

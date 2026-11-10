# AURORA — Tenant Onboarding Guide

This guide explains how to produce a new tenant pack, validate it, and load it into AURORA.

> **Warning:** Never upload real institutional data. All packs must have `data_origin: "synthetic"`. The validator enforces this; loading a pack without this field will fail.

---

## Overview

A tenant pack is a single JSON file that fully describes one university for AURORA. It contains:

- University metadata (name, time zone, clock format, term system, role vocabulary)
- Physical campus (buildings, rooms, walking times, covered routes)
- Courses and sections (with meetings, enrollment, roster)
- People (students, faculty, staff), teams, memberships
- Knowledge documents for the AI retriever
- Personas (demo actor mappings for the persona switcher)
- Campus events and terms

AURORA's backend uses the pack to seed an isolated SQLite database for the tenant. The same backend code runs for all tenants; no code changes are needed.

---

## Step 1: Produce a pack

### Use the generator (recommended)

```bash
cd aurora-campus-intelligence/backend
source .venv/bin/activate

python ../tools/generate_tenant_pack.py \
  --id my_university \
  --name "My University Demo" \
  --timezone "America/Chicago" \
  --clock 12 \
  --term semester \
  --out ../sample-data/tenants/my_university.pack.json
```

The generator creates a complete, valid pack with synthetic names and data. Customize the output JSON to change building names, room codes, knowledge documents, and personas.

### Write a pack manually

Use the format reference in `V3_PLATFORM_BRIEF.md` Appendix A, or inspect an existing pack:

```
sample-data/tenants/sbu_demo.pack.json
sample-data/tenants/rhine_demo.pack.json   # 24-hour clock, ECTS
sample-data/tenants/pacific_demo.pack.json  # quarter term system
```

Top-level keys required:

```json
{
  "schema_version": "tenant-pack/1",
  "data_origin": "synthetic",
  "generator": "manual",
  "tenant": { ... },
  "buildings": [ ... ],
  "walking_minutes": { ... },
  "covered_routes": [ ... ],
  "rooms": [ ... ],
  "assets": [ ... ],
  "services": [ ... ],
  "departments": [ ... ],
  "courses": [ ... ],
  "sections": [ ... ],
  "people": [ ... ],
  "teams": [ ... ],
  "memberships": [ ... ],
  "orgs": [ ... ],
  "campus_events": [ ... ],
  "terms": [ ... ],
  "knowledge": [ ... ],
  "personas": [ ... ]
}
```

---

## Step 2: Validate

Always validate before loading. The validator checks every constraint from the spec.

```bash
cd aurora-campus-intelligence/backend
source .venv/bin/activate

python ../tools/validate_tenant_pack.py ../sample-data/tenants/my_university.pack.json
```

### What the validator checks

| Check | Error message |
|---|---|
| `data_origin` ≠ `"synthetic"` | `data_origin must be "synthetic"` |
| Invalid IANA timezone | `invalid timezone` |
| Instructor double-booked | `instructor X double-booked` |
| Room double-booked | `room Y double-booked` |
| `enrolled` > `capacity` | `enrolled exceeds capacity` |
| `roster` size > `enrolled` headcount | `roster exceeds enrolled` |
| Missing walking pair | `missing walking pair` |
| Dangling persona reference | `dangling persona` |
| Fewer than 8 knowledge documents | `need at least 8 knowledge docs` |

Fix all errors before proceeding. A 7-item corruption test in `tests/test_u2_pack_loader.py` documents the expected error messages.

---

## Step 3: Load via CLI

```bash
cd aurora-campus-intelligence/backend
source .venv/bin/activate

# Load a single pack
python -m app.cli tenant load ../sample-data/tenants/my_university.pack.json

# Load all four sample packs
python -m app.cli tenant load \
  ../sample-data/tenants/sbu_demo.pack.json \
  ../sample-data/tenants/northbridge_demo.pack.json \
  ../sample-data/tenants/pacific_demo.pack.json \
  ../sample-data/tenants/rhine_demo.pack.json

# List all registered tenants
python -m app.cli tenant list

# Validate without loading
python -m app.cli tenant validate ../sample-data/tenants/my_university.pack.json

# Reset a tenant (drops and recreates the database)
python -m app.cli tenant reset my_university
```

### What the loader does

1. Validates the pack (same rules as `validate_tenant_pack.py`)
2. Backs up the existing tenant database to `data/backups/<timestamp>/` (if it exists)
3. Creates `data/tenants/<id>.db`
4. Seeds all entities: buildings, rooms, assets, services, departments, courses, sections, people, teams, memberships, orgs, events, terms
5. Builds `entity_links` from relationships (enrolled_in, teaches, member_of, etc.)
6. Loads knowledge documents into the FTS5 index for this tenant
7. Records `pack_hash` in the control plane

**Loading the same pack twice is a no-op** (idempotent): if the hash matches, the loader skips and returns immediately.

---

## Step 4: Switch to the new tenant

In the AURORA frontend, open the **Demo Universities** dropdown in the top bar. Your new tenant should appear.

To switch via API:

```bash
curl http://localhost:8000/tenant/config \
  -H "X-Demo-Tenant: my_university"
```

---

## Step 5: Test

```bash
cd aurora-campus-intelligence/backend
source .venv/bin/activate

# Run portability matrix (includes your new tenant if loaded)
pytest tests/test_u7_portability.py -v

# Run all tests
pytest -v
```

---

## Pack format reference

### `tenant` object

| Field | Type | Example | Notes |
|---|---|---|---|
| `id` | string | `"my_university"` | Slug, no spaces |
| `name` | string | `"My University Demo"` | Display name |
| `timezone` | string | `"America/Chicago"` | Valid IANA zone |
| `week_start` | string | `"monday"` | `monday` or `sunday` |
| `clock` | int | `12` | `12` or `24` |
| `term_system` | string | `"semester"` | `semester`, `quarter`, or `trimester` |
| `course_code_format` | string | `"{dept}{num}"` | Used in UI and responses |
| `room_code_format` | string | `"{bldg}-{num}"` | Used in UI and responses |
| `credit_unit` | string | `"credit hours"` | Displayed in UI |
| `role_vocabulary` | object | `{"facilities": "Campus Services"}` | Role display names |
| `min_cell_size` | int | `5` | Small-count suppression threshold |
| `features` | list | `["ics_import"]` | Feature flags |

### `knowledge` documents

Each document needs:

```json
{
  "id": "k001",
  "title": "Add/Drop Deadline",
  "body": "The last day to add or drop a course is October 15, 2026.",
  "tags": ["academic_calendar", "deadlines"],
  "last_verified": "2026-08-01"
}
```

At least 8 documents required. Documents are loaded into the tenant's FTS5 index and are only searchable within that tenant.

---

## Limitations

- Pack loading is one-way: once loaded, updating a pack requires `tenant reset` (which drops and rebuilds the database).
- The AURORA scenario (`disrupted_tuesday`) is tied to the SBU Demo timeline. Other tenants can run a generic simulation but the signature-day story is SBU-specific.
- No live connector exists; all data in a pack is static synthetic data.

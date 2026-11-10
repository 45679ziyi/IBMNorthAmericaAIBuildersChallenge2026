# AURORA — Tenancy and Authorization

This document describes the multi-tenant silo model and the authorization system implemented in AURORA V3.

---

## Tenancy model: the silo

AURORA uses a **silo model**: each tenant gets its own SQLite database file. There are no cross-tenant joins, no shared tables, and no tenant_id column on rows.

```
data/
  control.db            ← control plane: tenant registry only
  tenants/
    sbu_demo.db         ← Stony Brook Demo tenant database
    northbridge_demo.db ← Northbridge Demo tenant database
    pacific_demo.db     ← Pacific Demo tenant database
    rhine_demo.db       ← Rhine Demo tenant database
```

### How it works per request

1. Every HTTP request must carry the header `X-Demo-Tenant` (defaults to `sbu_demo` if absent).
2. `TenantMiddleware` in `app/main.py` looks up the slug in `control.db`.
3. If the tenant is not found, the request returns 404 (not 403; a non-existent tenant is not a forbidden resource).
4. The middleware installs a per-request `get_db` override pointing to the tenant's SQLite file.
5. All downstream code uses `get_db()` without knowing which file it points to.

If the test suite overrides `get_db` via `app.dependency_overrides`, the middleware detects this and skips its own override. Tests are always isolated to their in-memory fixture database.

### Isolation guarantees

- **Row isolation:** rows written to one tenant cannot be read by another (separate files).
- **FTS isolation:** the FTS5 knowledge index is per-tenant; a search in one tenant cannot return documents from another.
- **Clock isolation:** each tenant has its own virtual clock; advancing time in SBU Demo does not affect Rhine Demo.
- **Canary test:** `test_u1_tenancy.py::test_tenant_isolation` writes a row in tenant A and asserts it is not visible from tenant B.

### No `if tenant ==` branches

A test (`test_u7_portability.py::test_no_tenant_branch`) greps the entire codebase for `if tenant ==` and asserts zero matches. All tenant-specific behavior comes from configuration served by `GET /tenant/config` (time zone, clock format, credit unit, role vocabulary).

---

## Tenant pack format

Each university is described by a single validated JSON file (`*.pack.json`). The validator `tools/validate_tenant_pack.py` enforces:

- `schema_version`, `data_origin` must be `"synthetic"`, `generator` required
- `tenant.timezone` must be a valid IANA zone
- No room or instructor double-booked in section meetings
- `enrolled` ≤ `capacity` ≤ room capacity; `roster` ≤ `enrolled`
- Every building pair has a walking time; no dangling personas
- At least 8 knowledge documents

The backend replicates the same rules in `app/services/tenancy/pack_loader.py`. A test asserts both agree on all four packs.

---

## Authorization

### Principle

**Deny by default.** Every sensitive operation calls `authorize(actor, action, resource)` before executing. There is no "allow unless denied" path.

### ActorContext

Each request carries an `ActorContext` resolved from the `X-Demo-Actor` header:

| Field | Description |
|---|---|
| `actor_id` | Stable UUID for this persona |
| `role` | One of: `student`, `faculty`, `facilities`, `it`, `academic_ops`, `org_organizer` |
| `actor_mode` | `human` (default) or `autopilot` (Director mode) |
| `tenant_id` | Resolved from `X-Demo-Tenant` |

Unknown actor → 400 with a clear message. No authentication occurs; the persona selector is a demo tool only.

### Policy table

The policy table in `app/services/authz/__init__.py` declares rules of the form:

```python
PolicyRule(action, allowed_roles, denied_roles, reason_code)
```

Rules are evaluated in order; first match wins. Explicit `denied_roles` takes precedence over `allowed_roles`.

**Selected rules:**

| Action | Allowed | Explicitly denied | Reason code |
|---|---|---|---|
| `read:own_calendar` | student | — | `PERSONAL_DATA_STUDENT_ONLY` |
| `propose:room_change` | facilities | — | `FACILITIES_ONLY` |
| `approve:room_change` | academic_ops | **facilities** | `ACADOPS_ONLY` |
| `draft:course_update` | faculty | — | `FACULTY_ONLY` |
| `triage:incident` | facilities, it | — | `TRIAGE_ROLE_DENIED` |
| `ask:operations` | facilities, it, academic_ops | — | `OPS_SCOPE_DENIED` |
| `ask:personal` | student | — | `PERSONAL_SCOPE_STUDENT_ONLY` |
| `admin:*` | *(none)* | — | `ADMIN_ONLY` |

The key asymmetry: Facilities **proposes** room changes but **cannot approve** them. Academic Operations must approve. Attempting to approve as Facilities returns 403 with `reason_code: ACADOPS_ONLY`.

### Decision object

```python
Decision(
    allow: bool,
    reason_code: str,    # machine-readable, e.g. "ACADOPS_ONLY"
    reason: str,         # human sentence, e.g. "Only academic_ops may perform 'approve:room_change'..."
    scope: str | None,   # e.g. "team:facilities_team_sbu"
    redactions: list[str]  # fields stripped from the response
)
```

Every 403 response includes `reason_code` and `reason`. The frontend must not rely on hiding buttons as a security control; the server enforces.

### Small-count suppression

When returning counts of people (enrolled headcount, audience size, affected students), the rule is:

- count ≥ `min_cell_size` (default 5, configurable per tenant): return the count as-is
- count < `min_cell_size`: return the string `"fewer than 5"` (or `"fewer than N"`)

This prevents de-anonymization when a group is very small. The threshold comes from `tenant.min_cell_size` in the pack.

### Authorization matrix eval

The eval harness (`evals/__main__.py`) generates 300 test cases from the policy table and runs them. All 300 passed on the last run. See `docs/EVAL_REPORT.md`.

---

## Response headers

Every response carries:

| Header | Value |
|---|---|
| `X-Tenant` | The resolved tenant slug (e.g. `sbu_demo`) |
| `X-Auth-Mode` | `demo-persona` |

---

## Access log and privacy ledger

Any non-self read of person-level data (e.g., an instructor reading a section roster) writes an `AccessLog` row with:

- `accessor_id`, `accessor_role`
- `accessed_entity_type`, `accessed_entity_id`
- `purpose` (required; request is rejected without it)
- `tenant_id`, `ts_utc`

Students can retrieve their own ledger via `GET /privacy/ledger`.

---

## What is NOT implemented

- Real authentication (OIDC, SAML, passwords). The persona selector is a demo tool.
- Row-level security in SQLite (enforced by silo isolation instead).
- mTLS, JWTs, or any cryptographic auth mechanism.
- FERPA, GDPR, or any regulatory compliance.

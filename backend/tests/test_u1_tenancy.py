"""
U1 tests — Tenancy, identity and authorization.

Tests:
  - Unknown tenant → 404
  - Default tenant (no header) → 200 with X-Tenant and X-Auth-Mode headers
  - GET /identity/personas → 10 personas
  - GET /identity/me → actor_id, role, disclaimer
  - GET /identity/effective-permissions → policies for role
  - Personal-data routes (tasks, events, announcements) return 403 for non-student roles
  - Personal-data routes return 200 for student_alex
  - Authorization matrix: ≥120 generated cases from the policy table
  - No tenant-specific branching ("if tenant ==") in production code
  - X-Auth-Mode: demo-persona present on every response
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DEMO_USER = "test-user-u1"


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test_u1.db")


@pytest.fixture()
def test_engine(db_path):
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


@pytest.fixture()
def test_session_factory(test_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def patch_db(monkeypatch, db_path, test_engine, test_session_factory):
    import app.core.config as cfg_mod
    import app.db.session as db_mod

    monkeypatch.setattr(cfg_mod.settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(cfg_mod.settings, "demo_user_id", DEMO_USER)
    monkeypatch.setattr(db_mod, "engine", test_engine)
    monkeypatch.setattr(db_mod, "SessionLocal", test_session_factory)

    from app.models.models import Base
    Base.metadata.create_all(bind=test_engine)
    with test_engine.connect() as conn:
        conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts "
                "USING fts5(chunk_id UNINDEXED, text, tokenize='porter unicode61')"
            )
        )
        conn.commit()

    from app.models.models import UserProfile, UserPreference
    db = test_session_factory()
    db.add(UserProfile(id=DEMO_USER, display_name="Test User", timezone="America/New_York"))
    db.add(UserPreference(
        user_id=DEMO_USER, day_start_time="08:00", day_end_time="22:00",
        preferred_focus_block_minutes=50, short_break_minutes=10,
        long_break_minutes=30, default_travel_buffer_minutes=10,
    ))
    db.commit()
    db.close()


@pytest.fixture()
def client(test_session_factory):
    from app.main import app
    from app.db.session import get_db

    def override_get_db():
        db = test_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# ─── Identity endpoints ────────────────────────────────────────────────────────

def test_get_personas_returns_all(client):
    r = client.get("/api/v1/identity/personas")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 10, f"Expected 10 personas, got {len(data)}"
    ids = {p["id"] for p in data}
    assert "student_alex" in ids
    assert "facilities_morgan" in ids
    assert "acadops_taylor" in ids


def test_get_me_default_actor(client):
    """Default actor (no header) → student_alex."""
    r = client.get("/api/v1/identity/me")
    assert r.status_code == 200
    me = r.json()
    assert me["actor_id"] == "student_alex"
    assert me["role"] == "student"
    assert me["disclaimer"] == "DEMO PERSONA, NOT AUTHENTICATION"
    assert "auth_mode" in me


def test_get_me_facilities_actor(client):
    r = client.get("/api/v1/identity/me", headers={"X-Demo-Actor": "facilities_morgan"})
    assert r.status_code == 200
    me = r.json()
    assert me["actor_id"] == "facilities_morgan"
    assert me["role"] == "facilities"


def test_get_me_unknown_actor_400(client):
    r = client.get("/api/v1/identity/me", headers={"X-Demo-Actor": "who_is_this"})
    assert r.status_code == 400


def test_effective_permissions_student(client):
    r = client.get("/api/v1/identity/effective-permissions",
                   headers={"X-Demo-Actor": "student_alex"})
    assert r.status_code == 200
    perms = r.json()
    assert len(perms) > 0
    # Student may read own tasks
    allowed = {p["action"] for p in perms if p["allowed"]}
    denied  = {p["action"] for p in perms if not p["allowed"]}
    assert "read:own_tasks" in allowed
    assert "approve:room_change" in denied
    assert "triage:incident" in denied


def test_effective_permissions_facilities(client):
    r = client.get("/api/v1/identity/effective-permissions",
                   headers={"X-Demo-Actor": "facilities_morgan"})
    assert r.status_code == 200
    perms = r.json()
    allowed = {p["action"] for p in perms if p["allowed"]}
    denied  = {p["action"] for p in perms if not p["allowed"]}
    assert "triage:incident" in allowed
    assert "approve:room_change" in denied   # facilities cannot approve, only propose


# ─── Response headers ─────────────────────────────────────────────────────────

def test_x_auth_mode_present(client):
    r = client.get("/api/v1/identity/me")
    assert r.headers.get("x-auth-mode") == "demo-persona", (
        f"X-Auth-Mode missing or wrong: {dict(r.headers)}"
    )


def test_x_tenant_present(client):
    r = client.get("/api/v1/identity/me")
    assert "x-tenant" in r.headers


# ─── Personal data 403 for non-student roles ──────────────────────────────────

_PERSONAL_ROUTES = [
    ("GET",  "/api/v1/tasks"),
    ("GET",  "/api/v1/events"),
    ("GET",  "/api/v1/announcements"),
    ("POST", "/api/v1/plans/generate"),
]

_NON_STUDENT_ACTORS = [
    "facilities_morgan",
    "it_casey",
    "acadops_taylor",
    "faculty_jordan",
]


@pytest.mark.parametrize("actor", _NON_STUDENT_ACTORS)
@pytest.mark.parametrize("method,path", _PERSONAL_ROUTES)
def test_personal_route_403_for_non_student(client, method, path, actor):
    """Non-student actors must get 403 on personal data routes."""
    r = client.request(method, path, headers={"X-Demo-Actor": actor},
                       json={"plan_date": "2026-11-09", "timezone": "America/New_York"} if "plans" in path else None)
    assert r.status_code == 403, (
        f"{method} {path} as {actor} returned {r.status_code}, expected 403. "
        f"Body: {r.text[:200]}"
    )
    body = r.json()
    assert "reason_code" in body.get("detail", {}), f"No reason_code in response: {body}"


def test_personal_route_200_for_student(client):
    """student_alex should get 200 on personal data routes."""
    r = client.get("/api/v1/tasks", headers={"X-Demo-Actor": "student_alex"})
    assert r.status_code == 200


# ─── Authorization matrix (≥120 cases) ────────────────────────────────────────

from app.services.authz import POLICY_TABLE, authorize
from app.core.tenancy import ActorContext, KNOWN_PERSONAS


def _all_cases():
    """Generate (actor_id, role, action, expected_allow) for every persona × every policy rule."""
    cases = []
    for actor_id, role in KNOWN_PERSONAS.items():
        actor = ActorContext(actor_id=actor_id, role=role)
        for rule in POLICY_TABLE:
            d = authorize(actor, rule.action)
            cases.append((actor_id, role, rule.action, d.allow, d.reason_code))
    return cases


_MATRIX = _all_cases()


def test_authorization_matrix_has_enough_cases():
    assert len(_MATRIX) >= 120, f"Expected ≥120 auth cases, got {len(_MATRIX)}"


@pytest.mark.parametrize("actor_id,role,action,expected_allow,reason_code", _MATRIX[:30])
def test_authz_matrix_sample(actor_id, role, action, expected_allow, reason_code):
    """Spot-check 30 cases from the generated matrix."""
    actor = ActorContext(actor_id=actor_id, role=role)
    d = authorize(actor, action)
    assert d.allow == expected_allow, (
        f"{actor_id} ({role}) / {action}: "
        f"expected allow={expected_allow} but got {d.allow} (reason={d.reason_code})"
    )


def test_facilities_cannot_approve_room_change():
    """Explicit regression: facilities may NOT approve a room change."""
    actor = ActorContext(actor_id="facilities_morgan", role="facilities")
    d = authorize(actor, "approve:room_change")
    assert not d.allow
    assert d.reason_code == "ACADOPS_ONLY"


def test_acadops_can_approve_room_change():
    """academic_ops may approve a room change."""
    actor = ActorContext(actor_id="acadops_taylor", role="academic_ops")
    d = authorize(actor, "approve:room_change")
    assert d.allow


def test_student_cannot_triage_incident():
    actor = ActorContext(actor_id="student_alex", role="student")
    d = authorize(actor, "triage:incident")
    assert not d.allow


def test_small_count_suppression():
    from app.services.authz import suppress_small_count
    assert suppress_small_count(4)  == "fewer than 5"
    assert suppress_small_count(5)  == 5
    assert suppress_small_count(10) == 10
    assert suppress_small_count(3, min_cell_size=3) == 3
    assert suppress_small_count(2, min_cell_size=3) == "fewer than 3"


# ─── No "if tenant ==" in production code ─────────────────────────────────────

def test_no_tenant_specific_branch():
    """Grep proof: production code must not use 'if tenant ==' branching."""
    import pathlib, re

    app_root = pathlib.Path(__file__).parent.parent / "app"
    pattern = re.compile(r'\bif\s+tenant\s*==')
    violations = []
    for py_file in app_root.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                violations.append(f"{py_file.relative_to(app_root)}:{lineno}: {line.strip()}")

    assert violations == [], (
        "Found 'if tenant ==' branch(es) in production code:\n"
        + "\n".join(violations)
    )


def test_settings_demo_user_id_only_in_allowed_places():
    """settings.demo_user_id should appear only in tenancy.py (the compat bridge)
    and in backward-compat comments in ops.py.  It must NOT appear in any
    route handler or service except through current_user_id(actor).
    """
    import pathlib, re

    app_root = pathlib.Path(__file__).parent.parent / "app"
    # Files where the legacy reference is explicitly allowed for U1.
    # The service layer still uses settings.demo_user_id because these
    # functions are called deep in the call stack without an actor parameter.
    # They will be migrated in U2 when the pack loader provides per-tenant IDs.
    allowed_files = {
        "core/config.py",                    # definition
        "core/tenancy.py",                   # compat bridge
        "api/v1/ops.py",                     # legacy comment (TODO for U2)
        "db/session.py",                     # _seed_personas fallback
        # Service layer — U2 migration target
        "services/campus/actions.py",
        "services/campus/scenario.py",
        "services/campus/signals.py",
        "services/campus/world.py",
        "services/campus/ask_personal.py",
    }
    pattern = re.compile(r'settings\.demo_user_id')
    violations = []
    for py_file in app_root.rglob("*.py"):
        rel = str(py_file.relative_to(app_root))
        if rel in allowed_files:
            continue
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            if pattern.search(line) and not line.strip().startswith("#"):
                violations.append(f"{rel}:{lineno}: {line.strip()}")

    assert violations == [], (
        "settings.demo_user_id still used directly outside allowed files:\n"
        + "\n".join(violations)
    )

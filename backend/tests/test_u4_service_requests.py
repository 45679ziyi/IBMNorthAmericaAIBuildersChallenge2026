"""
U4 tests — Service requests state machine and team routing.

Tests:
  - create → auto-routed to team (when EntityLink owner_team exists)
  - non-requester GET → 404 (no information leakage)
  - transition: submitted → triaged → in_progress → resolved
  - illegal transition → 409
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

ACTOR_STUDENT   = "student_alex"
ACTOR_FACILITIES = "facilities_morgan"


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test_u4_sr.db")


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
    monkeypatch.setattr(cfg_mod.settings, "demo_user_id", ACTOR_STUDENT)
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
    db.add(UserProfile(id=ACTOR_STUDENT, display_name="Alex", timezone="America/New_York"))
    db.add(UserPreference(
        user_id=ACTOR_STUDENT, day_start_time="08:00", day_end_time="22:00",
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


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _seed_team_and_link(session_factory, team_id: str = "team_it", service_id: str = "wifi"):
    """Create a team and entity_link so auto-routing works."""
    from app.models.models import Team, EntityLink
    db = session_factory()
    db.add(Team(id=team_id, name="IT Team", role_type="it", scope_type="service"))
    db.add(EntityLink(
        from_type="service", from_id=service_id,
        rel="owner_team", to_type="team", to_id=team_id,
    ))
    db.commit()
    db.close()


def _create_sr(client, service_id: str = "wifi", actor: str = ACTOR_STUDENT,
               title: str = "WiFi broken") -> dict:
    r = client.post(
        "/api/v1/service-requests",
        json={"service_id": service_id, "title": title, "body": "Please fix"},
        headers={"X-Demo-Actor": actor},
    )
    assert r.status_code == 201, f"SR creation failed: {r.status_code} {r.text}"
    return r.json()


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_create_service_request(client, test_session_factory):
    """POST /service-requests → 201, returns service request with submitted status."""
    sr = _create_sr(client)
    assert sr["status"] == "submitted"
    assert sr["requester_person_id"] == ACTOR_STUDENT
    assert sr["service_id"] == "wifi"


def test_create_auto_routes_to_team(client, test_session_factory):
    """When EntityLink owner_team exists, assigned_team_id is set."""
    _seed_team_and_link(test_session_factory)
    sr = _create_sr(client)
    assert sr["assigned_team_id"] == "team_it"


def test_create_no_team_link(client, test_session_factory):
    """Without owner_team link, assigned_team_id is None."""
    sr = _create_sr(client, service_id="unknown_service")
    assert sr["assigned_team_id"] is None


def test_list_service_requests_requester_sees_own(client, test_session_factory):
    """Requester can list their own service requests."""
    _create_sr(client, title="First request")
    _create_sr(client, title="Second request")

    r = client.get("/api/v1/service-requests", headers={"X-Demo-Actor": ACTOR_STUDENT})
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 2


def test_non_requester_get_individual_404(client, test_session_factory):
    """A different actor (not requester, not team member) cannot find the SR — 404."""
    sr = _create_sr(client)
    sr_id = sr["id"]

    # faculty_jordan is not the requester and not in any team
    r = client.get("/api/v1/service-requests", headers={"X-Demo-Actor": "faculty_jordan"})
    assert r.status_code == 200
    data = r.json()
    # faculty_jordan should not see student_alex's request
    ids = [s["id"] for s in data]
    assert sr_id not in ids, "Non-requester should not see SR"


def test_transition_submitted_to_triaged(client, test_session_factory):
    """submitted → triaged is a valid transition."""
    sr = _create_sr(client)
    r = client.post(
        f"/api/v1/service-requests/{sr['id']}/transition",
        json={"target_status": "triaged"},
        headers={"X-Demo-Actor": ACTOR_STUDENT},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "triaged"


def test_transition_full_chain(client, test_session_factory):
    """submitted → triaged → in_progress → resolved (full happy path)."""
    sr = _create_sr(client)
    sr_id = sr["id"]
    for target in ("triaged", "in_progress", "resolved"):
        r = client.post(
            f"/api/v1/service-requests/{sr_id}/transition",
            json={"target_status": target},
            headers={"X-Demo-Actor": ACTOR_STUDENT},
        )
        assert r.status_code == 200, f"Transition to {target} failed: {r.text}"
        assert r.json()["status"] == target


def test_illegal_transition_returns_409(client, test_session_factory):
    """submitted → resolved (skipping triaged/in_progress) → 409."""
    sr = _create_sr(client)
    r = client.post(
        f"/api/v1/service-requests/{sr['id']}/transition",
        json={"target_status": "resolved"},
        headers={"X-Demo-Actor": ACTOR_STUDENT},
    )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["reason_code"] == "illegal_transition"


def test_transition_to_same_status_409(client, test_session_factory):
    """Transitioning to the current status is illegal."""
    sr = _create_sr(client)
    r = client.post(
        f"/api/v1/service-requests/{sr['id']}/transition",
        json={"target_status": "submitted"},
        headers={"X-Demo-Actor": ACTOR_STUDENT},
    )
    assert r.status_code == 409


def test_version_increments_on_transition(client, test_session_factory):
    """Version is incremented on each transition (optimistic lock signal)."""
    sr = _create_sr(client)
    initial_version = sr["version"]
    r = client.post(
        f"/api/v1/service-requests/{sr['id']}/transition",
        json={"target_status": "triaged"},
        headers={"X-Demo-Actor": ACTOR_STUDENT},
    )
    assert r.json()["version"] == initial_version + 1


def test_team_member_can_transition(client, test_session_factory):
    """A team member assigned to the SR can transition it."""
    from app.models.models import Team, EntityLink, TeamMembership
    db = test_session_factory()
    db.add(Team(id="team_fac", name="Facilities", role_type="facilities", scope_type="service"))
    db.add(EntityLink(
        from_type="service", from_id="hvac",
        rel="owner_team", to_type="team", to_id="team_fac",
    ))
    db.add(TeamMembership(
        person_id=ACTOR_FACILITIES, team_id="team_fac",
    ))
    db.commit()
    db.close()

    sr = _create_sr(client, service_id="hvac", actor=ACTOR_STUDENT)
    r = client.post(
        f"/api/v1/service-requests/{sr['id']}/transition",
        json={"target_status": "triaged"},
        headers={"X-Demo-Actor": ACTOR_FACILITIES},
    )
    assert r.status_code == 200

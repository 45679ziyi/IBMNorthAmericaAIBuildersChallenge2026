"""
V4-01 / V4-02 security regression tests.

Tests:
  - Thread non-participant gets exactly 403 (Finding G strict).
  - Service Request: unrelated staff role cannot see another user's request (Finding B).
  - audience_for: empty entity_refs → empty audience (not role-wide).
  - audience_for: scoped_to links → only team members in audience.
  - audience_for: no scoped_to link → empty facilities/IT audience (not role-wide).
  - Canonical event tenant is server-resolved; body tenant_id is ignored (Finding F).
  - Service request tenant is server-resolved (Finding F).
"""
from __future__ import annotations

import hashlib
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

ACTOR_STUDENT    = "student_alex"
ACTOR_FACILITIES = "facilities_morgan"
ACTOR_IT         = "it_casey"
ACTOR_ACADOPS    = "acadops_taylor"
ACTOR_FACULTY    = "faculty_jordan"


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test_v4_authz.db")


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

def _make_event(sf, last_actor=ACTOR_FACILITIES, entity_refs=None) -> str:
    from app.models.models import CanonicalEvent
    db = sf()
    key = hashlib.sha256(f"v4-{last_actor}-{entity_refs}".encode()).hexdigest()
    ce = CanonicalEvent(
        type="incident.hvac_fault",
        idempotency_key=key,
        tenant_id="sbu_demo",
        last_actor=last_actor,
        entity_refs_json=json.dumps(entity_refs or []),
    )
    db.add(ce)
    db.commit()
    ce_id = ce.id
    db.close()
    return ce_id


def _make_team_and_member(sf, team_id: str, person_id: str, role: str, scoped_to_type: str, scoped_to_id: str):
    """Create a team, person, membership, and scoped_to link."""
    from app.models.models import EntityLink, Person, Team, TeamMembership
    db = sf()
    if db.get(Team, team_id) is None:
        db.add(Team(id=team_id, name=team_id, role_type=role, scope_type=scoped_to_type,
                    scope_id=scoped_to_id, data_origin="synthetic"))
    if db.get(Person, person_id) is None:
        db.add(Person(id=person_id, display_name=person_id, role=role, data_origin="synthetic"))
    existing_m = db.query(TeamMembership).filter_by(person_id=person_id, team_id=team_id).first()
    if existing_m is None:
        db.add(TeamMembership(person_id=person_id, team_id=team_id, is_lead=False))
    # scoped_to link
    existing_l = db.query(EntityLink).filter_by(
        from_type="team", from_id=team_id, rel="scoped_to",
        to_type=scoped_to_type, to_id=scoped_to_id
    ).first()
    if existing_l is None:
        db.add(EntityLink(from_type="team", from_id=team_id, rel="scoped_to",
                          to_type=scoped_to_type, to_id=scoped_to_id))
    db.commit()
    db.close()


# ─── Tests: Thread participant check (Finding A/G) ────────────────────────────

def test_thread_non_participant_gets_exactly_403(client, test_session_factory):
    """V4-01 (Finding G): non-participant gets exactly 403, not 201.

    Event created by facilities_morgan. student_alex is neither the last_actor
    nor in any audience (empty entity_refs → empty audience from V4-02).
    """
    ce_id = _make_event(test_session_factory, last_actor=ACTOR_FACILITIES)
    r = client.post(
        f"/api/v1/canonical-events/{ce_id}/thread",
        json={"body": "Unauthorized message"},
        headers={"X-Demo-Actor": ACTOR_STUDENT},
    )
    assert r.status_code == 403, (
        f"Expected 403 (non-participant), got {r.status_code}. "
        "Empty audience must not become allow-all."
    )


def test_thread_last_actor_allowed(client, test_session_factory):
    """V4-01 positive: last_actor is always a participant."""
    ce_id = _make_event(test_session_factory, last_actor=ACTOR_FACILITIES)
    r = client.post(
        f"/api/v1/canonical-events/{ce_id}/thread",
        json={"body": "I created this"},
        headers={"X-Demo-Actor": ACTOR_FACILITIES},
    )
    assert r.status_code == 201, r.text


def test_thread_unrelated_it_gets_403(client, test_session_factory):
    """V4-01 (Finding A): IT role alone does not grant thread access to unrelated events."""
    ce_id = _make_event(test_session_factory, last_actor=ACTOR_FACILITIES)
    r = client.post(
        f"/api/v1/canonical-events/{ce_id}/thread",
        json={"body": "IT trying to access facilities event"},
        headers={"X-Demo-Actor": ACTOR_IT},
    )
    assert r.status_code == 403, (
        f"Expected 403 for IT actor on unrelated event, got {r.status_code}."
    )


# ─── Tests: Service Request authorization (Finding B) ────────────────────────

def test_sr_requester_can_see_own_request(client):
    """Requester can see their own service request."""
    r = client.post(
        "/api/v1/service-requests",
        json={"service_id": "svc_wifi", "title": "WiFi issue", "body": ""},
        headers={"X-Demo-Actor": ACTOR_STUDENT},
    )
    assert r.status_code == 201, r.text
    sr_id = r.json()["id"]

    r2 = client.get("/api/v1/service-requests", headers={"X-Demo-Actor": ACTOR_STUDENT})
    ids = [sr["id"] for sr in r2.json()]
    assert sr_id in ids


def test_sr_unrelated_staff_cannot_see_other_request(client):
    """V4-01 (Finding B): unrelated staff (facilities) cannot see student's request.

    facilities_morgan has no team membership with assigned_team of this SR.
    The request is auto-routed to a team only if EntityLink owner_team exists.
    With no such link, assigned_team_id is None → only requester sees it.
    """
    r = client.post(
        "/api/v1/service-requests",
        json={"service_id": "svc_wifi_no_team", "title": "Private request", "body": ""},
        headers={"X-Demo-Actor": ACTOR_STUDENT},
    )
    assert r.status_code == 201, r.text
    sr_id = r.json()["id"]

    r2 = client.get("/api/v1/service-requests", headers={"X-Demo-Actor": ACTOR_FACILITIES})
    ids = [sr["id"] for sr in r2.json()]
    assert sr_id not in ids, (
        "facilities_morgan should not see student_alex's request (no team assignment)."
    )


# ─── Tests: audience_for scoped resolution (Finding C / V4-02) ───────────────

def test_audience_empty_entity_refs_gives_empty_audience(test_session_factory):
    """V4-02: event with no entity_refs → audience is empty for all roles."""
    from app.services.graph import audience_for
    from app.models.models import CanonicalEvent

    db = test_session_factory()
    ce = CanonicalEvent(
        type="incident.generic",
        idempotency_key="v402-empty-refs",
        tenant_id="sbu_demo",
        last_actor=ACTOR_FACILITIES,
        entity_refs_json="[]",
    )
    db.add(ce)
    db.commit()

    aud = audience_for(db, ce)
    db.close()

    for role, ids in aud.items():
        assert ids == [], (
            f"Expected empty audience for role '{role}' with no entity_refs; "
            f"got {ids}. Empty entity_refs must not produce role-wide audience."
        )


def test_audience_scoped_team_member_in_facilities_audience(test_session_factory):
    """V4-02 (Finding C): facilities audience resolved via scoped_to building link."""
    from app.services.graph import audience_for
    from app.models.models import CanonicalEvent, EntityLink

    # Set up: team scoped to building B1, member is facilities_morgan
    _make_team_and_member(
        test_session_factory,
        team_id="team_facilities_B1",
        person_id=ACTOR_FACILITIES,
        role="facilities",
        scoped_to_type="building",
        scoped_to_id="B1",
    )
    # room in building B1
    db = test_session_factory()
    db.add(EntityLink(from_type="room", from_id="R101", rel="in_building",
                      to_type="building", to_id="B1"))
    db.commit()

    # Event references building B1 directly
    ce = CanonicalEvent(
        type="incident.hvac_fault",
        idempotency_key="v402-scoped-B1",
        tenant_id="sbu_demo",
        last_actor=ACTOR_FACILITIES,
        entity_refs_json=json.dumps([{"type": "building", "id": "B1"}]),
    )
    db.add(ce)
    db.commit()

    aud = audience_for(db, ce)
    db.close()

    assert ACTOR_FACILITIES in aud["facilities"], (
        f"Expected facilities_morgan in facilities audience via scoped_to; "
        f"got {aud['facilities']}"
    )


def test_audience_no_scoped_to_gives_empty_facilities(test_session_factory):
    """V4-02 (Finding C): no scoped_to link → facilities audience is empty.

    This proves no role-wide fallback: even if facilities_morgan exists as
    a Person with role=facilities, they must NOT appear in the audience
    without an explicit scoped_to link.
    """
    from app.services.graph import audience_for
    from app.models.models import CanonicalEvent, EntityLink, Person

    # Create facilities_morgan Person WITHOUT any team/scoped_to link
    db = test_session_factory()
    if db.get(Person, ACTOR_FACILITIES) is None:
        db.add(Person(id=ACTOR_FACILITIES, display_name="Morgan",
                      role="facilities", data_origin="synthetic"))
    # Add a building entity link for room to building (but NO team scoped_to)
    db.add(EntityLink(from_type="room", from_id="R_UNOWNED", rel="in_building",
                      to_type="building", to_id="B_UNOWNED"))
    db.commit()

    ce = CanonicalEvent(
        type="incident.hvac_fault",
        idempotency_key="v402-no-scope",
        tenant_id="sbu_demo",
        last_actor="someone_else",
        entity_refs_json=json.dumps([{"type": "building", "id": "B_UNOWNED"}]),
    )
    db.add(ce)
    db.commit()

    aud = audience_for(db, ce)
    db.close()

    assert aud["facilities"] == [], (
        f"Expected empty facilities audience when no team is scoped to B_UNOWNED; "
        f"got {aud['facilities']}. Role-wide fallback must be absent."
    )


# ─── Tests: Tenant ID from server context (Finding F) ────────────────────────

def test_canonical_event_tenant_from_server_not_body(client):
    """V4-01 (Finding F): tenant_id in canonical event is from X-Demo-Tenant header,
    not from the request body (body no longer has a tenant_id field).
    """
    r = client.post(
        "/api/v1/canonical-events",
        # No tenant_id in body — server resolves from header
        json={
            "type": "incident.test_tenant",
            "severity": "low",
            "source_record_id": "v401-tenant-test",
        },
        headers={"X-Demo-Actor": ACTOR_FACILITIES, "X-Demo-Tenant": "sbu_demo"},
    )
    assert r.status_code == 201, r.text
    # The returned tenant_id must be sbu_demo (server-resolved)
    data = r.json()
    assert data.get("tenant_id") == "sbu_demo"


def test_service_request_tenant_from_server(client):
    """V4-01 (Finding F): service request tenant_id from actor.tenant_id, not body."""
    r = client.post(
        "/api/v1/service-requests",
        json={"service_id": "svc_test", "title": "Tenant test SR"},
        headers={"X-Demo-Actor": ACTOR_STUDENT, "X-Demo-Tenant": "sbu_demo"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data.get("tenant_id") == "sbu_demo"

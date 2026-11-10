"""
U3 tests — Canonical events, work items, and workflow engine.

Tests:
  - Idempotent ingest: POST /canonical-events twice returns same canonical_id
  - Correlation: student report joins a Wi-Fi event (corroborations=1, no second event)
  - canonical_id consistent across different role projections
  - POST /work-items/{id}/transition illegal transition returns 409
  - facilities cannot approve room_reassignment (403 with reason_code)
  - acadops can approve room_reassignment
  - version conflict returns 409
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DEMO_USER = "test-user-u3"


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test_u3.db")


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


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ingest(client, payload: dict, actor: str = "facilities_morgan") -> dict:
    """POST to /canonical-events and return response JSON."""
    r = client.post(
        "/api/v1/canonical-events",
        json=payload,
        headers={"X-Demo-Actor": actor},
    )
    assert r.status_code in (200, 201), f"Ingest failed: {r.status_code} {r.text}"
    return r.json()


def _wifi_payload(source_record_id: str = "wifi-001", correlation_id: str = None) -> dict:
    p = {
        "type": "service_disruption.wifi",
        "severity": "high",
        "source_feed": "it_monitor",
        "source_record_id": source_record_id,
        "entity_refs": [{"type": "service", "id": "wifi"}],
        "classification": "institutional",
        "payload": {"affected_buildings": ["SB_MAIN"]},
    }
    if correlation_id:
        p["correlation_id"] = correlation_id
    return p


# ─── Idempotency tests ────────────────────────────────────────────────────────

def test_idempotent_ingest_returns_same_id(client):
    """POST /canonical-events twice with same source_record_id → same id."""
    payload = _wifi_payload()

    r1 = _ingest(client, payload)
    ce_id1 = r1["id"]
    assert ce_id1.startswith("ce_"), f"Expected ce_ prefix: {ce_id1}"

    r2 = _ingest(client, payload)
    ce_id2 = r2["id"]

    assert ce_id1 == ce_id2, (
        f"Idempotency failed: first call returned {ce_id1!r}, second returned {ce_id2!r}"
    )


def test_idempotent_ingest_different_record_id_creates_new(client):
    """Two different source_record_ids → two different canonical events."""
    r1 = _ingest(client, _wifi_payload("wifi-001"))
    r2 = _ingest(client, _wifi_payload("wifi-002"))
    assert r1["id"] != r2["id"]


# ─── Correlation tests ────────────────────────────────────────────────────────

def test_correlation_increments_corroborations(client):
    """Student report joining an existing Wi-Fi event via correlation_id."""
    # First event (IT monitor creates the disruption)
    initial = _ingest(client, _wifi_payload("wifi-master", correlation_id="corr-wifi-1"))
    ce_id = initial["id"]
    assert initial["corroborations"] == 0

    # Second event (student corroboration via different source_record_id,
    # same correlation_id)
    corroboration_payload = _wifi_payload(
        source_record_id="student-report-001",
        correlation_id="corr-wifi-1",
    )
    # student_alex reports it
    r2 = _ingest(client, corroboration_payload, actor="student_alex")

    # Must return the SAME canonical event
    assert r2["id"] == ce_id, (
        f"Corroboration should return existing event {ce_id!r}, got {r2['id']!r}"
    )
    assert r2["corroborations"] == 1, (
        f"corroborations should be 1, got {r2['corroborations']}"
    )


def test_correlation_no_duplicate_event(client, test_session_factory):
    """After correlation, only one CanonicalEvent row exists."""
    from app.models.models import CanonicalEvent

    _ingest(client, _wifi_payload("wifi-orig", correlation_id="corr-wifi-dedup"))
    _ingest(client, _wifi_payload("wifi-corr", correlation_id="corr-wifi-dedup"),
            actor="student_alex")

    db = test_session_factory()
    count = db.query(CanonicalEvent).count()
    db.close()
    assert count == 1, f"Expected 1 CanonicalEvent, got {count}"


# ─── Role projection tests ────────────────────────────────────────────────────

def test_canonical_id_consistent_across_projections(client):
    """The same canonical event id is returned regardless of actor role."""
    payload = _wifi_payload("wifi-proj")
    ce_id = _ingest(client, payload)["id"]

    # Check various roles return same id
    for actor in ("student_alex", "facilities_morgan", "it_casey", "acadops_taylor"):
        r = client.get(
            f"/api/v1/canonical-events/{ce_id}",
            headers={"X-Demo-Actor": actor},
        )
        assert r.status_code == 200, f"Actor {actor}: {r.status_code} {r.text}"
        assert r.json()["id"] == ce_id, f"Actor {actor}: id mismatch"


def test_get_canonical_event_not_found(client):
    r = client.get("/api/v1/canonical-events/ce_nonexistent",
                   headers={"X-Demo-Actor": "facilities_morgan"})
    assert r.status_code == 404


# ─── Reach endpoint tests ─────────────────────────────────────────────────────

def test_reach_endpoint(client):
    """GET /canonical-events/{id}/reach returns audience_counts."""
    ce_id = _ingest(client, _wifi_payload("wifi-reach"))["id"]
    r = client.get(
        f"/api/v1/canonical-events/{ce_id}/reach",
        headers={"X-Demo-Actor": "it_casey"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "audience_counts" in data
    assert "canonical_event_id" in data
    assert data["canonical_event_id"] == ce_id


# ─── Work item creation tests ─────────────────────────────────────────────────

def test_ingest_creates_work_item(client, test_session_factory):
    """POST /canonical-events for a service_disruption creates a WorkItem."""
    from app.models.models import WorkItem

    ce = _ingest(client, _wifi_payload("wifi-wi"))
    ce_id = ce["id"]

    db = test_session_factory()
    wi = db.query(WorkItem).filter(WorkItem.canonical_event_id == ce_id).first()
    db.close()

    assert wi is not None, "WorkItem should be created on ingest"
    assert wi.workflow_type == "service_disruption"
    assert wi.status == "reported"


# ─── Workflow transition tests ────────────────────────────────────────────────

def _make_room_reassignment_work_item(test_session_factory) -> str:
    """Directly create a room_reassignment WorkItem in 'proposed' status."""
    from app.models.models import WorkItem
    db = test_session_factory()
    wi = WorkItem(
        workflow_type="room_reassignment",
        status="proposed",
        version=1,
        tenant_id="sbu_demo",
    )
    db.add(wi)
    db.commit()
    wi_id = wi.id
    db.close()
    return wi_id


def test_illegal_transition_returns_409(client, test_session_factory):
    """POST /work-items/{id}/transition with wrong action → 409."""
    wi_id = _make_room_reassignment_work_item(test_session_factory)

    r = client.post(
        f"/api/v1/work-items/{wi_id}/transition",
        json={"action": "approve"},  # approve from 'proposed' is illegal
        headers={"X-Demo-Actor": "acadops_taylor"},
    )
    assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text}"
    body = r.json()
    assert "reason_code" in body["detail"]
    assert body["detail"]["reason_code"] == "ILLEGAL_TRANSITION"


def test_facilities_cannot_approve_room_reassignment(client, test_session_factory):
    """facilities role cannot approve a room_reassignment — 403."""
    from app.models.models import WorkItem
    db = test_session_factory()
    # Put the work item in awaiting_approval status
    wi = WorkItem(
        workflow_type="room_reassignment",
        status="awaiting_approval",
        version=1,
        tenant_id="sbu_demo",
    )
    db.add(wi)
    db.commit()
    wi_id = wi.id
    db.close()

    r = client.post(
        f"/api/v1/work-items/{wi_id}/transition",
        json={"action": "approve", "payload": {"approval_note": "ok"}},
        headers={"X-Demo-Actor": "facilities_morgan"},
    )
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
    body = r.json()
    assert "reason_code" in body["detail"]
    assert body["detail"]["reason_code"] == "ROLE_DENIED"


def test_acadops_can_approve_room_reassignment(client, test_session_factory):
    """academic_ops role can approve a room_reassignment."""
    from app.models.models import WorkItem
    db = test_session_factory()
    wi = WorkItem(
        workflow_type="room_reassignment",
        status="awaiting_approval",
        version=1,
        tenant_id="sbu_demo",
    )
    db.add(wi)
    db.commit()
    wi_id = wi.id
    db.close()

    r = client.post(
        f"/api/v1/work-items/{wi_id}/transition",
        json={"action": "approve", "payload": {"approval_note": "Approved by acadops"}},
        headers={"X-Demo-Actor": "acadops_taylor"},
    )
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["to_status"] == "approved"


def test_version_conflict_returns_409(client, test_session_factory):
    """Providing wrong expected_version → 409 VERSION_CONFLICT."""
    from app.models.models import WorkItem
    db = test_session_factory()
    wi = WorkItem(
        workflow_type="room_reassignment",
        status="awaiting_approval",
        version=1,
        tenant_id="sbu_demo",
    )
    db.add(wi)
    db.commit()
    wi_id = wi.id
    db.close()

    r = client.post(
        f"/api/v1/work-items/{wi_id}/transition",
        json={
            "action": "approve",
            "payload": {"approval_note": "Approved"},
            "expected_version": 99,  # wrong version
        },
        headers={"X-Demo-Actor": "acadops_taylor"},
    )
    assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text}"
    body = r.json()
    assert body["detail"]["reason_code"] == "VERSION_CONFLICT"


def test_successful_transition_increments_version(client, test_session_factory):
    """Successful transition increments the work item version."""
    from app.models.models import WorkItem
    db = test_session_factory()
    wi = WorkItem(
        workflow_type="incident_response",
        status="reported",
        version=1,
        tenant_id="sbu_demo",
    )
    db.add(wi)
    db.commit()
    wi_id = wi.id
    db.close()

    r = client.post(
        f"/api/v1/work-items/{wi_id}/transition",
        json={"action": "start_triage"},
        headers={"X-Demo-Actor": "facilities_morgan"},
    )
    assert r.status_code == 200
    assert r.json()["version"] == 2


def test_list_work_items_role_scope(client, test_session_factory):
    """GET /work-items returns only workflow types allowed for the actor's role."""
    from app.models.models import WorkItem
    db = test_session_factory()
    # Create one of each type
    for wf_type, status in [
        ("incident_response", "reported"),
        ("room_reassignment", "proposed"),
        ("course_update", "drafted"),
        ("service_request", "submitted"),
    ]:
        db.add(WorkItem(workflow_type=wf_type, status=status, version=1, tenant_id="sbu_demo"))
    db.commit()
    db.close()

    # facilities should see incident_response and room_reassignment (and service disruption and service request)
    r = client.get("/api/v1/work-items", headers={"X-Demo-Actor": "facilities_morgan"})
    assert r.status_code == 200
    types = {item["workflow_type"] for item in r.json()}
    assert "incident_response" in types
    assert "room_reassignment" in types
    # facilities should NOT see course_update
    assert "course_update" not in types


def test_workflow_audit_trail(client, test_session_factory):
    """Each transition creates a WorkItemTransition audit record."""
    from app.models.models import WorkItem, WorkItemTransition
    db = test_session_factory()
    wi = WorkItem(
        workflow_type="incident_response",
        status="reported",
        version=1,
        tenant_id="sbu_demo",
    )
    db.add(wi)
    db.commit()
    wi_id = wi.id
    db.close()

    # Make a transition
    r = client.post(
        f"/api/v1/work-items/{wi_id}/transition",
        json={"action": "start_triage"},
        headers={"X-Demo-Actor": "it_casey"},
    )
    assert r.status_code == 200

    db = test_session_factory()
    transitions = db.query(WorkItemTransition).filter(
        WorkItemTransition.work_item_id == wi_id
    ).all()
    db.close()

    assert len(transitions) == 1
    t = transitions[0]
    assert t.from_status == "reported"
    assert t.to_status == "triage"
    assert t.actor_id == "it_casey"
    assert t.actor_role == "it"
    assert t.actor_mode == "human"

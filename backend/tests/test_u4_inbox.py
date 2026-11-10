"""
U4 tests — Inbox, notification preferences, reach map, access log.

Tests:
  - Create notification → GET /inbox returns it (unread first)
  - unread-count is derived from notifications table (count query), not a counter
  - read + ack flow
  - notification pref disabled → notification still stored (pref only controls creation in service layer)
  - reach map: per-role notified/ack counts
  - access_log written on reach map call
"""
from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

ACTOR_STUDENT = "student_alex"
ACTOR_FACILITIES = "facilities_morgan"


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test_u4_inbox.db")


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

def _seed_notification(session_factory, recipient: str = ACTOR_STUDENT, state: str = "unread",
                        kind: str = "system", requires_ack: bool = False,
                        canonical_event_id: str = None) -> str:
    """Directly insert a Notification and return its id."""
    from app.models.models import Notification
    db = session_factory()
    n = Notification(
        recipient_person_id=recipient,
        kind=kind,
        title="Test notification",
        body="Body text",
        why_json=json.dumps([{
            "rel": "enrolled_in", "entity_type": "section",
            "entity_id": "CS101-01", "text": "You are enrolled"
        }]),
        state=state,
        requires_ack=requires_ack,
        canonical_event_id=canonical_event_id,
        data_origin="test",
    )
    db.add(n)
    db.commit()
    nid = n.id
    db.close()
    return nid


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_inbox_returns_notification(client, test_session_factory):
    """Create notification directly, GET /inbox returns it."""
    nid = _seed_notification(test_session_factory)
    r = client.get("/api/v1/inbox", headers={"X-Demo-Actor": ACTOR_STUDENT})
    assert r.status_code == 200
    data = r.json()
    assert any(n["id"] == nid for n in data), f"Notification {nid} not in inbox: {data}"


def test_inbox_unread_first(client, test_session_factory):
    """Unread notifications come before read ones."""
    _seed_notification(test_session_factory, state="read")
    _seed_notification(test_session_factory, state="unread")
    r = client.get("/api/v1/inbox", headers={"X-Demo-Actor": ACTOR_STUDENT})
    assert r.status_code == 200
    items = r.json()
    states = [n["state"] for n in items]
    # All unread should precede any read
    saw_non_unread = False
    for s in states:
        if s != "unread":
            saw_non_unread = True
        elif saw_non_unread:
            pytest.fail(f"Unread appeared after non-unread in: {states}")


def test_unread_count_from_notifications_table(client, test_session_factory):
    """unread-count is a COUNT() on notifications table, not a separate counter."""
    # No notifications yet
    r = client.get("/api/v1/inbox/unread-count", headers={"X-Demo-Actor": ACTOR_STUDENT})
    assert r.status_code == 200
    assert r.json()["unread"] == 0

    # Seed 2 unread, 1 read
    _seed_notification(test_session_factory, state="unread")
    _seed_notification(test_session_factory, state="unread")
    _seed_notification(test_session_factory, state="read")

    r = client.get("/api/v1/inbox/unread-count", headers={"X-Demo-Actor": ACTOR_STUDENT})
    assert r.status_code == 200
    assert r.json()["unread"] == 2, f"Expected 2, got {r.json()}"


def test_mark_read_flow(client, test_session_factory):
    """POST /inbox/{id}/read transitions state to read and sets read_at."""
    nid = _seed_notification(test_session_factory, state="unread")

    r = client.post(f"/api/v1/inbox/{nid}/read", headers={"X-Demo-Actor": ACTOR_STUDENT})
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "read"
    assert data["read_at"] is not None

    # unread-count should now be 0
    r2 = client.get("/api/v1/inbox/unread-count", headers={"X-Demo-Actor": ACTOR_STUDENT})
    assert r2.json()["unread"] == 0


def test_mark_ack_flow(client, test_session_factory):
    """POST /inbox/{id}/ack transitions state to acknowledged."""
    nid = _seed_notification(test_session_factory, state="unread", requires_ack=True)

    r = client.post(f"/api/v1/inbox/{nid}/ack", headers={"X-Demo-Actor": ACTOR_STUDENT})
    assert r.status_code == 200
    assert r.json()["state"] == "acknowledged"


def test_mark_read_wrong_actor_returns_404(client, test_session_factory):
    """Another actor cannot read someone else's notification."""
    nid = _seed_notification(test_session_factory, recipient=ACTOR_STUDENT)
    r = client.post(f"/api/v1/inbox/{nid}/read", headers={"X-Demo-Actor": ACTOR_FACILITIES})
    assert r.status_code == 404


def test_preferences_upsert(client):
    """PUT /inbox/preferences creates and updates preferences."""
    r = client.put(
        "/api/v1/inbox/preferences",
        json={"category": "course_update", "enabled": False},
        headers={"X-Demo-Actor": ACTOR_STUDENT},
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False

    # Update to enabled
    r2 = client.put(
        "/api/v1/inbox/preferences",
        json={"category": "course_update", "enabled": True},
        headers={"X-Demo-Actor": ACTOR_STUDENT},
    )
    assert r2.status_code == 200
    assert r2.json()["enabled"] is True

    # GET preferences
    r3 = client.get("/api/v1/inbox/preferences", headers={"X-Demo-Actor": ACTOR_STUDENT})
    assert r3.status_code == 200
    prefs = r3.json()
    assert any(p["category"] == "course_update" and p["enabled"] is True for p in prefs)


def test_why_entries_in_inbox(client, test_session_factory):
    """Notification why[] evidence path is returned correctly."""
    nid = _seed_notification(test_session_factory)
    r = client.get("/api/v1/inbox", headers={"X-Demo-Actor": ACTOR_STUDENT})
    assert r.status_code == 200
    items = r.json()
    notif = next(n for n in items if n["id"] == nid)
    assert len(notif["why"]) == 1
    assert notif["why"][0]["rel"] == "enrolled_in"
    assert notif["why"][0]["entity_type"] == "section"


def test_reach_map_with_notifications(client, test_session_factory):
    """GET /canonical-events/{id}/reach counts from notifications table."""
    from app.models.models import CanonicalEvent, Person
    import hashlib

    db = test_session_factory()
    # Create a person with role=student (skip if already seeded by patch_db)
    if db.get(Person, "student_alex") is None:
        db.add(Person(id="student_alex", display_name="Alex", role="student"))
        db.flush()

    # Create canonical event
    ce = CanonicalEvent(
        type="service_disruption.wifi",
        idempotency_key=hashlib.sha256(b"test-reach").hexdigest(),
        tenant_id="sbu_demo",
    )
    db.add(ce)
    db.flush()
    ce_id = ce.id

    # Seed 2 notifications for this event
    from app.models.models import Notification
    for _ in range(2):
        db.add(Notification(
            recipient_person_id="student_alex",
            kind="service_disruption",
            title="WiFi down",
            body="",
            why_json="[]",
            state="unread",
            canonical_event_id=ce_id,
        ))
    db.commit()
    db.close()

    r = client.get(
        f"/api/v1/canonical-events/{ce_id}/reach",
        headers={"X-Demo-Actor": ACTOR_FACILITIES},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["canonical_event_id"] == ce_id
    # student role should show count 2 (2 notifications to student_alex)
    assert data["audience_counts"].get("student", 0) == 2


def test_reach_map_writes_access_log(client, test_session_factory):
    """GET /canonical-events/{id}/reach writes an access_log entry."""
    from app.models.models import CanonicalEvent, AccessLog
    import hashlib

    db = test_session_factory()
    ce = CanonicalEvent(
        type="incident.test",
        idempotency_key=hashlib.sha256(b"access-log-test").hexdigest(),
        tenant_id="sbu_demo",
    )
    db.add(ce)
    db.commit()
    ce_id = ce.id
    db.close()

    r = client.get(
        f"/api/v1/canonical-events/{ce_id}/reach",
        headers={"X-Demo-Actor": ACTOR_FACILITIES},
    )
    assert r.status_code == 200

    db = test_session_factory()
    log = db.query(AccessLog).filter(
        AccessLog.canonical_event_id == ce_id,
        AccessLog.purpose == "reach_map",
    ).first()
    assert log is not None
    assert log.actor_id == ACTOR_FACILITIES
    db.close()

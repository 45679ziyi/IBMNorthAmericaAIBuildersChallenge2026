"""Backend tests for AURORA — planner, ICS, API, and RAG.

Uses a temp-file SQLite DB so all connections (app startup, overridden get_db,
test helpers) share the same physical database.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DEMO_USER = "test-user-0001"

# ─── Per-test temp database ──────────────────────────────────────────────────

@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test_aurora.db")


@pytest.fixture()
def test_engine(db_path):
    eng = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    return eng


@pytest.fixture()
def test_session_factory(test_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def patch_db(monkeypatch, db_path, test_engine, test_session_factory):
    """Redirect the whole app to use the temp DB before any test runs."""
    import app.core.config as cfg_mod
    import app.db.session as db_mod

    # Point settings at the temp DB
    monkeypatch.setattr(cfg_mod.settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(cfg_mod.settings, "demo_user_id", DEMO_USER)

    # Swap the module-level engine and factory
    monkeypatch.setattr(db_mod, "engine", test_engine)
    monkeypatch.setattr(db_mod, "SessionLocal", test_session_factory)

    # Create all tables + FTS in the temp DB
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

    # Seed demo user + preferences
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
def client(monkeypatch, test_engine, test_session_factory):
    """Return a TestClient whose dependency override yields from the temp DB."""
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


# ─── Health ──────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "disclaimer" in data


# ─── Task CRUD ───────────────────────────────────────────────────────────────

def test_create_and_list_task(client):
    r = client.post("/api/v1/tasks", json={
        "title": "Test task",
        "estimated_minutes": 45,
        "priority": "high",
        "status": "todo",
        "source_type": "manual",
    })
    assert r.status_code == 201
    task_id = r.json()["id"]

    r2 = client.get("/api/v1/tasks")
    ids = [t["id"] for t in r2.json()]
    assert task_id in ids


def test_update_task(client):
    r = client.post("/api/v1/tasks", json={"title": "Original", "estimated_minutes": 30})
    tid = r.json()["id"]
    r2 = client.put(f"/api/v1/tasks/{tid}", json={"status": "done"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "done"


def test_delete_task(client):
    r = client.post("/api/v1/tasks", json={"title": "To delete", "estimated_minutes": 15})
    tid = r.json()["id"]
    r2 = client.delete(f"/api/v1/tasks/{tid}")
    assert r2.status_code == 204
    r3 = client.get("/api/v1/tasks")
    assert not any(t["id"] == tid for t in r3.json())


def test_task_not_found(client):
    r = client.put("/api/v1/tasks/nonexistent-id", json={"status": "done"})
    assert r.status_code == 404


# ─── Calendar events ─────────────────────────────────────────────────────────

def test_create_and_list_event(client):
    r = client.post("/api/v1/events", json={
        "title": "CSE 213 Lecture",
        "start_at_utc": "2026-11-03T14:30:00Z",
        "end_at_utc": "2026-11-03T15:50:00Z",
        "event_type": "class",
        "source_type": "manual",
    })
    assert r.status_code == 201
    eid = r.json()["id"]
    r2 = client.get("/api/v1/events")
    assert any(e["id"] == eid for e in r2.json())


def test_event_end_before_start_rejected(client):
    r = client.post("/api/v1/events", json={
        "title": "Bad event",
        "start_at_utc": "2026-11-03T15:00:00Z",
        "end_at_utc": "2026-11-03T14:00:00Z",
    })
    assert r.status_code == 400


# ─── ICS import ──────────────────────────────────────────────────────────────

SAMPLE_ICS_PATH = Path(__file__).parent.parent.parent / "sample-data" / "demo_calendar.ics"


def test_ics_import_valid(client):
    if not SAMPLE_ICS_PATH.exists():
        pytest.skip("Sample ICS not found")
    with open(SAMPLE_ICS_PATH, "rb") as f:
        r = client.post("/api/v1/events/import/ics", files={"file": ("demo_calendar.ics", f, "text/calendar")})
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] >= 1
    assert isinstance(data["events"], list)


def test_ics_import_wrong_extension(client):
    r = client.post("/api/v1/events/import/ics", files={"file": ("test.txt", b"not a calendar", "text/plain")})
    assert r.status_code == 400


def test_ics_import_oversized(client):
    big = b"X" * (3 * 1024 * 1024)  # 3 MB
    r = client.post("/api/v1/events/import/ics", files={"file": ("too_big.ics", big, "text/calendar")})
    assert r.status_code == 400


# ─── Planner ─────────────────────────────────────────────────────────────────

def test_planner_no_overlap(client):
    """Generated plan must have no overlapping blocks."""
    for i in range(3):
        client.post("/api/v1/tasks", json={
            "title": f"Task {i}",
            "estimated_minutes": 30,
            "priority": "normal",
        })
    r = client.post("/api/v1/plans/generate", json={"plan_date": "2026-11-10", "timezone": "America/New_York"})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "draft"
    blocks = sorted(data["blocks"], key=lambda b: b["start_at_utc"])
    for i in range(len(blocks) - 1):
        a, b = blocks[i], blocks[i + 1]
        a_end = datetime.fromisoformat(a["end_at_utc"])
        b_start = datetime.fromisoformat(b["start_at_utc"])
        assert b_start >= a_end, f"Overlap: {a['title']} ends at {a_end}, {b['title']} starts at {b_start}"


def test_planner_fixed_events_not_moved(client):
    """Fixed events must not be altered by the planner."""
    ev_r = client.post("/api/v1/events", json={
        "title": "Fixed Class",
        "start_at_utc": "2026-11-10T14:00:00Z",
        "end_at_utc": "2026-11-10T15:30:00Z",
        "event_type": "class",
    })
    eid = ev_r.json()["id"]
    r = client.post("/api/v1/plans/generate", json={"plan_date": "2026-11-10", "timezone": "America/New_York"})
    data = r.json()
    fixed = [b for b in data["blocks"] if b["block_type"] == "fixed_event" and b["calendar_event_id"] == eid]
    assert len(fixed) == 1, "Fixed event must appear as a fixed_event block"


def test_planner_completed_tasks_not_scheduled(client):
    t = client.post("/api/v1/tasks", json={"title": "Done task", "estimated_minutes": 30, "status": "done"})
    tid = t.json()["id"]
    r = client.post("/api/v1/plans/generate", json={"plan_date": "2026-11-11", "timezone": "America/New_York"})
    task_blocks = [b for b in r.json()["blocks"] if b.get("task_id") == tid]
    assert len(task_blocks) == 0, "Completed task must not be scheduled"


def test_planner_deterministic(client):
    """Same inputs → same plan structure (task count)."""
    client.post("/api/v1/tasks", json={"title": "Det task", "estimated_minutes": 40})
    r1 = client.post("/api/v1/plans/generate", json={"plan_date": "2026-11-12", "timezone": "America/New_York"})
    r2 = client.post("/api/v1/plans/generate", json={"plan_date": "2026-11-12", "timezone": "America/New_York"})
    t1 = len([b for b in r1.json()["blocks"] if b["block_type"] == "task"])
    t2 = len([b for b in r2.json()["blocks"] if b["block_type"] == "task"])
    assert t1 == t2


def test_plan_accept_reject(client):
    r = client.post("/api/v1/plans/generate", json={"plan_date": "2026-11-13", "timezone": "America/New_York"})
    pid = r.json()["id"]
    ra = client.post(f"/api/v1/plans/{pid}/accept")
    assert ra.status_code == 200
    assert ra.json()["status"] == "accepted"
    # Cannot reject after accepted
    rr = client.post(f"/api/v1/plans/{pid}/reject")
    assert rr.status_code == 400


# ─── RAG assistant ────────────────────────────────────────────────────────────

def _seed_knowledge_test(session_factory):
    from app.models.models import KnowledgeDocument, KnowledgeChunk
    db = session_factory()
    try:
        doc = KnowledgeDocument(
            id="test-doc-1",
            title="Test FERPA Document",
            publisher="SBU Registrar",
            canonical_url="https://www.stonybrook.edu/registrar/info/ferpa.html",
            content_text="FERPA is a Federal law protecting student education records.",
            usage_note="Test",
            is_active=True,
        )
        db.add(doc)
        db.flush()
        chunk = KnowledgeChunk(
            id="test-doc-1-chunk-0",
            document_id="test-doc-1",
            chunk_index=0,
            text="FERPA is a Federal law protecting student education records.",
            search_text="ferpa is a federal law protecting student education records.",
        )
        db.add(chunk)
        db.execute(
            text("INSERT OR REPLACE INTO knowledge_chunks_fts(chunk_id, text) VALUES (:cid, :txt)"),
            {"cid": "test-doc-1-chunk-0", "txt": "FERPA is a Federal law protecting student education records."},
        )
        db.commit()
    finally:
        db.close()


def test_assistant_known_question(client, test_session_factory):
    _seed_knowledge_test(test_session_factory)
    r = client.post("/api/v1/assistant/ask", json={"question": "What is FERPA?"})
    assert r.status_code == 200
    data = r.json()
    assert data["coverage"] in ("supported", "partial")
    assert len(data["sources"]) >= 1
    assert "stonybrook.edu" in data["sources"][0]["url"]


def test_assistant_unknown_question(client):
    r = client.post("/api/v1/assistant/ask", json={"question": "What is the population of Mars?"})
    assert r.status_code == 200
    data = r.json()
    assert data["coverage"] == "not_found"


def test_assistant_short_question_rejected(client):
    r = client.post("/api/v1/assistant/ask", json={"question": "hi"})
    assert r.status_code == 422


# ─── Privacy labels ───────────────────────────────────────────────────────────

def test_connectors_include_demo_labels(client):
    r = client.get("/api/v1/connectors/status")
    assert r.status_code == 200
    data = r.json()
    demo_conns = [c for c in data if c["status"] == "demo"]
    assert len(demo_conns) >= 1, "At least one connector should be labeled demo"


def test_campus_pulse_synthetic(client):
    r = client.get("/api/v1/campus-pulse/demo")
    assert r.status_code == 200
    for reading in r.json():
        assert reading["data_origin"] == "synthetic", "All campus pulse readings must be synthetic"

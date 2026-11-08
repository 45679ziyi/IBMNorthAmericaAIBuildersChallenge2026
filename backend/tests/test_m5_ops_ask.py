"""
M5 tests: ops impact endpoints and personal-context Ask.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DEMO_USER = "test-user-0001"


# ─── DB / client fixtures (same pattern as test_m3) ──────────────────────────

@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test_m5.db")


@pytest.fixture()
def test_engine(db_path):
    eng = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    return eng


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
def client(monkeypatch, test_engine, test_session_factory):
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


# ─── Ops impact tests ─────────────────────────────────────────────────────────

def test_impact_numbers(client):
    """inc-hvac-jav101: 2 classes, 168 students, one feasible room JAV-102."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "10:10"})
    impact = client.get("/api/v1/ops/incidents/inc-hvac-jav101/impact").json()
    assert impact["total_students"] == 168
    assert len(impact["affected_classes"]) == 2
    assert len(impact["feasible_mitigations"]) == 1
    assert impact["feasible_mitigations"][0]["room_id"] == "JAV-102"


def test_staff_approval_emits_signal(client):
    """Approving the mitigation at 10:10 creates the room_change signal for MAT 203."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "10:10"})
    r = client.post("/api/v1/ops/incidents/inc-hvac-jav101/approve-mitigation")
    assert r.status_code == 200
    assert r.json()["status"] == "executed_simulated"
    # MAT 203 should now show JAV-102
    events = client.get("/api/v1/events").json()
    mat203 = next(e for e in events if "MAT 203" in e["title"])
    assert "JAV" in mat203["location_text"] or "102" in mat203["location_text"]


def test_scripted_approval_fires_at_1035(client):
    """If nobody manually approves, the scripted approval at 10:35 resolves the incident."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "10:40"})
    events = client.get("/api/v1/events").json()
    mat203 = next(e for e in events if "MAT 203" in e["title"])
    assert "JAV" in mat203["location_text"] or "102" in mat203["location_text"]


def test_incidents_empty_without_scenario(client):
    """Without a scenario, /ops/incidents returns empty list."""
    client.post("/api/v1/sim/stop")
    r = client.get("/api/v1/ops/incidents")
    assert r.status_code == 200
    assert r.json() == []


def test_impact_without_scenario(client):
    """Without a scenario, impact endpoint returns 200 with empty classes."""
    client.post("/api/v1/sim/stop")
    r = client.get("/api/v1/ops/incidents/inc-hvac-jav101/impact")
    assert r.status_code == 200
    data = r.json()
    assert data["affected_classes"] == []
    assert data["total_students"] == 0


# ─── Personal-context Ask tests ───────────────────────────────────────────────

def test_ask_next_commitment_at_0920(client):
    """At 09:20, 'where do I need to be next?' returns CSE 214, Javits 101, leave-by 9:51 AM."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "09:20"})
    r = client.post("/api/v1/assistant/ask", json={"question": "Where do I need to be next?"})
    assert r.status_code == 200
    data = r.json()
    assert data["coverage"] in ("supported", "partial")
    answer = data["answer"].lower()
    assert "cse 214" in answer or "javits" in answer


def test_ask_what_changed(client):
    """At 09:20, 'what changed today?' mentions the CSE 214 room change."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "09:20"})
    r = client.post("/api/v1/assistant/ask", json={"question": "What changed today?"})
    assert r.status_code == 200
    data = r.json()
    assert data["coverage"] in ("supported", "partial")
    answer = data["answer"].lower()
    assert "cse 214" in answer or "room" in answer or "javits" in answer


def test_ask_unknown_falls_back_to_public_retriever(client):
    """An unknown question (no intent match) falls back to the public knowledge retriever (not personal context)."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    r = client.post("/api/v1/assistant/ask", json={"question": "What is FERPA?"})
    assert r.status_code == 200
    data = r.json()
    # Should NOT be a personal-context answer (disclaimer would contain "campus data")
    assert "campus data" not in data.get("disclaimer", "")
    # Coverage can be not_found if no KB seeded — just ensure it's a valid value
    assert data["coverage"] in ("supported", "partial", "not_found")


def test_ask_persona_less_real_mode(client):
    """In real mode (no scenario), personal intents return partial or not_found gracefully."""
    client.post("/api/v1/sim/stop")
    r = client.post("/api/v1/assistant/ask", json={"question": "Where do I need to be next?"})
    assert r.status_code == 200  # should not crash
    data = r.json()
    assert data["coverage"] in ("partial", "not_found")

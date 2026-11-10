"""
U3 tests — Director mode, autopilot, step invariance.

Tests:
  - step_invariance: 1-min steps, 5-min steps, single jump, reset-replay → same state hash
  - autopilot skips steps already executed by human
  - take-over switches persona
  - actor_mode="autopilot" appears in audit
"""
from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DEMO_USER = "test-user-u3d"


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test_u3d.db")


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

def _start_scenario(client) -> dict:
    r = client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    assert r.status_code == 200, f"start failed: {r.status_code} {r.text}"
    return r.json()


def _advance(client, minutes: int) -> dict:
    r = client.post("/api/v1/sim/advance", json={"minutes": minutes})
    assert r.status_code == 200, f"advance failed: {r.status_code} {r.text}"
    return r.json()


def _advance_to(client, time_str: str) -> dict:
    r = client.post("/api/v1/sim/advance", json={"to": time_str})
    assert r.status_code == 200, f"advance_to failed: {r.status_code} {r.text}"
    return r.json()


def _reset(client) -> dict:
    r = client.post("/api/v1/sim/reset")
    assert r.status_code == 200, f"reset failed: {r.status_code} {r.text}"
    return r.json()


def _state_hash(test_session_factory) -> str:
    """Compute a hash of all applied signal IDs — used to verify step invariance."""
    from app.models.models import SimState, Signal
    db = test_session_factory()
    state = db.get(SimState, 1)
    signals = db.query(Signal).order_by(Signal.at_utc, Signal.id).all()
    db.close()

    applied_ids = sorted(json.loads(state.applied_signal_ids or "[]")) if state else []
    signal_ids = [s.id for s in signals]

    canonical = json.dumps({
        "applied": applied_ids,
        "signals": signal_ids,
    }, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


# ─── Director mode endpoints ──────────────────────────────────────────────────

def test_director_mode_default_is_off(client):
    """SimState starts with director_mode=off."""
    r = client.get("/api/v1/sim/state")
    assert r.status_code == 200
    state = r.json()
    assert state.get("director_mode", "off") == "off"


def test_set_director_autopilot(client):
    """POST /sim/director with mode=autopilot sets director_mode."""
    r = client.post("/api/v1/sim/director", json={"mode": "autopilot"})
    assert r.status_code == 200
    assert r.json()["director_mode"] == "autopilot"


def test_set_director_off(client):
    """POST /sim/director with mode=off disables director."""
    # First set to autopilot
    client.post("/api/v1/sim/director", json={"mode": "autopilot"})
    # Then turn off
    r = client.post("/api/v1/sim/director", json={"mode": "off"})
    assert r.status_code == 200
    assert r.json()["director_mode"] == "off"


def test_set_director_invalid_mode(client):
    """POST /sim/director with invalid mode → 400."""
    r = client.post("/api/v1/sim/director", json={"mode": "invalid"})
    assert r.status_code == 400


def test_take_over(client):
    """POST /sim/take-over switches active persona and disables autopilot."""
    # Start in autopilot
    client.post("/api/v1/sim/director", json={"mode": "autopilot"})

    r = client.post("/api/v1/sim/take-over", json={"persona": "facilities_morgan"})
    assert r.status_code == 200
    state = r.json()
    assert state["active_persona"] == "facilities_morgan"
    assert state["director_mode"] == "off"


def test_take_over_unknown_persona(client):
    """POST /sim/take-over with unknown persona → 400."""
    r = client.post("/api/v1/sim/take-over", json={"persona": "unknown_persona"})
    assert r.status_code == 400


def test_take_over_missing_persona(client):
    """POST /sim/take-over with no persona → 400."""
    r = client.post("/api/v1/sim/take-over", json={})
    assert r.status_code == 400


# ─── Autopilot audit trail ────────────────────────────────────────────────────

def test_autopilot_actor_mode_in_audit(test_session_factory):
    """WorkItemTransitions executed by autopilot have actor_mode='autopilot'."""
    from app.models.models import WorkItem, WorkItemTransition
    from app.core.tenancy import ActorContext
    from app.services.workflows.engine import engine as wf_engine, TransitionRequest

    db = test_session_factory()
    # Create a work item and advance it via autopilot actor
    wi = WorkItem(
        workflow_type="incident_response",
        status="reported",
        version=1,
        tenant_id="sbu_demo",
    )
    db.add(wi)
    db.commit()

    actor = ActorContext(actor_id="facilities_morgan", role="facilities")
    req = TransitionRequest(
        action="start_triage",
        payload={},
        actor_mode="autopilot",
    )
    wf_engine.advance(db, wi, req, actor)
    db.commit()

    transitions = db.query(WorkItemTransition).filter(
        WorkItemTransition.work_item_id == wi.id
    ).all()
    db.close()

    assert len(transitions) == 1
    assert transitions[0].actor_mode == "autopilot"
    assert transitions[0].actor_id == "facilities_morgan"


# ─── Step invariance tests ────────────────────────────────────────────────────

def test_step_invariance_1min_vs_5min(client, test_session_factory):
    """Advancing 1 min at a time to 08:30 produces same state as 5 min at a time."""
    # Run 1: 1-minute steps from 07:00 to 08:30 = 90 steps
    _start_scenario(client)
    for _ in range(90):
        _advance(client, 1)
    hash_1min = _state_hash(test_session_factory)

    # Reset and run 2: 5-minute steps to 08:30 = 18 steps
    _reset(client)
    for _ in range(18):
        _advance(client, 5)
    hash_5min = _state_hash(test_session_factory)

    assert hash_1min == hash_5min, (
        f"step_invariance failed: 1-min hash={hash_1min}, 5-min hash={hash_5min}"
    )


def test_step_invariance_single_jump(client, test_session_factory):
    """Single jump to 08:30 produces same state as incremental steps."""
    # Run 1: 1-minute steps to 08:30
    _start_scenario(client)
    for _ in range(90):
        _advance(client, 1)
    hash_incremental = _state_hash(test_session_factory)

    # Reset and run 2: single jump to 08:30
    _reset(client)
    _advance_to(client, "08:30")
    hash_jump = _state_hash(test_session_factory)

    assert hash_incremental == hash_jump, (
        f"step_invariance failed: incremental hash={hash_incremental}, jump hash={hash_jump}"
    )


def test_step_invariance_reset_replay(client, test_session_factory):
    """Two full replays from reset produce identical state hashes."""
    # Run 1
    _start_scenario(client)
    _advance_to(client, "10:00")
    hash_run1 = _state_hash(test_session_factory)

    # Reset and run again
    _reset(client)
    _advance_to(client, "10:00")
    hash_run2 = _state_hash(test_session_factory)

    assert hash_run1 == hash_run2, (
        f"step_invariance failed: run1 hash={hash_run1}, run2 hash={hash_run2}"
    )


def test_autopilot_skips_human_executed_steps(client, test_session_factory):
    """Autopilot does not re-execute steps already done by a human."""
    from app.models.models import WorkItemTransition

    # Start scenario and create a work item, execute a transition as human
    _start_scenario(client)

    # Ingest a canonical event to create a work item
    r = client.post(
        "/api/v1/canonical-events",
        json={
            "type": "service_disruption.wifi",
            "severity": "high",
            "source_feed": "it_monitor",
            "source_record_id": "wifi-autopilot-test",
            "entity_refs": [],
            "classification": "institutional",
            "payload": {},
        },
        headers={"X-Demo-Actor": "it_casey"},
    )
    assert r.status_code in (200, 201)
    ce_id = r.json()["id"]

    # Find the work item
    from app.models.models import WorkItem
    db = test_session_factory()
    wi = db.query(WorkItem).filter(WorkItem.canonical_event_id == ce_id).first()
    assert wi is not None
    wi_id = wi.id
    db.close()

    # Human transitions it to triage
    r = client.post(
        f"/api/v1/work-items/{wi_id}/transition",
        json={"action": "start_triage"},
        headers={"X-Demo-Actor": "it_casey"},
    )
    assert r.status_code == 200

    db = test_session_factory()
    transitions_before = db.query(WorkItemTransition).filter(
        WorkItemTransition.work_item_id == wi_id
    ).count()
    db.close()

    # Enable autopilot and advance — should not re-execute the already-done step
    client.post("/api/v1/sim/director", json={"mode": "autopilot"})
    _advance(client, 5)

    db = test_session_factory()
    transitions_after = db.query(WorkItemTransition).filter(
        WorkItemTransition.work_item_id == wi_id
    ).count()
    wi_after = db.get(WorkItem, wi_id)
    db.close()

    # Status should not have changed back/re-executed
    assert wi_after.status == "triage", f"Status should remain 'triage', got '{wi_after.status}'"
    # No duplicate transition
    assert transitions_after == transitions_before

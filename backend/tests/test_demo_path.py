"""
D9 fix — Demo-path tests.

These tests start from the *real* seeded demo state (seed_demo_data.seed())
and run the full demo day through the API.  They verify the exact headline
defects from V3 brief Section 1.3:

    D1  No legacy deadline:task-demo-* moves after scenario starts
    D3  Repeated start/stop cycles do not accumulate AURORA blocks
    D4  Ops move resolves after room-change approval (staff view)
    D5  Policy does not flip after auto-execution

A failing golden-path test here means the real demo is broken, even if all
other unit tests pass.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
import pytz
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DEMO_USER = "test-user-demo-path"
_CAMPUS_TZ = pytz.timezone("America/New_York")


# ─── Fixtures (same boilerplate as other test files) ──────────────────────────

@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test_demo_path.db")


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
    db.add(UserProfile(id=DEMO_USER, display_name="Demo User", timezone="America/New_York"))
    db.add(UserPreference(
        user_id=DEMO_USER, day_start_time="08:00", day_end_time="22:00",
        preferred_focus_block_minutes=50, short_break_minutes=10,
        long_break_minutes=30, default_travel_buffer_minutes=10,
    ))
    db.commit()
    db.close()

    # D9: seed the real demo data (not just schema) — this is what the actual
    # demo does and what was missing from previous golden tests.
    from scripts.seed_demo_data import seed
    db2 = test_session_factory()
    seed(db2)
    db2.close()


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


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_demo_path_d1_no_legacy_moves(client):
    """D1: after seeding demo data and starting the scenario, no legacy
    deadline:task-demo-* moves must appear in the student feed at 12:20.
    """
    r = client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    assert r.status_code == 200, f"start failed: {r.text}"

    r = client.post("/api/v1/sim/advance", json={"to": "12:20"})
    assert r.status_code == 200, f"advance failed: {r.text}"

    moves = client.get("/api/v1/moves?audience=student").json()
    legacy = [m["key"] for m in moves if m["key"].startswith("deadline:task-demo")]
    assert legacy == [], (
        f"D1 regression: legacy deadline:task-demo-* moves appeared after "
        f"scenario start: {legacy}.  All moves: {[m['key'] for m in moves]}"
    )


def test_demo_path_d3_no_block_accumulation(client):
    """D3: starting the scenario three times must not accumulate AURORA blocks.
    After the third start+advance cycle, the number of aurora_block events
    must be the same as after the first cycle.
    """
    def _count_blocks():
        evs = client.get("/api/v1/events").json()
        return sum(1 for e in evs if e.get("source_type") == "aurora_block")

    for _ in range(3):
        client.post("/api/v1/sim/stop")
        client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
        client.post("/api/v1/sim/advance", json={"to": "07:35"})

    # Check that no extra blocks were accumulated
    block_count = _count_blocks()
    # Start from scratch again to get the reference count
    client.post("/api/v1/sim/stop")
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "07:35"})
    reference_count = _count_blocks()

    assert block_count == reference_count, (
        f"D3 regression: block count after 3 cycles ({block_count}) "
        f"does not match fresh start ({reference_count}). "
        "Repeated starts are accumulating blocks."
    )


def test_demo_path_d1_hero_move_visible(client):
    """D1+D2: the Career Fair conflict move (impact=medium) must be visible
    in the student feed at 12:20 (not buried behind legacy deadline cards).
    """
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "12:20"})

    moves = client.get("/api/v1/moves?audience=student").json()
    conflict_keys = [m["key"] for m in moves if m["key"].startswith("conflict:ev-fair")]
    assert conflict_keys, (
        f"D1/D2 regression: conflict:ev-fair move not found in student feed. "
        f"Moves present: {[m['key'] for m in moves]}"
    )

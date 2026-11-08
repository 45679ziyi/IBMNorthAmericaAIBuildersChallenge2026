"""M1 tests: clock, scenario seeding, signals, relevance."""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DEMO_USER = "test-user-0001"

# ─── Per-test temp database (mirrors test_api.py) ────────────────────────────

@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test_m1.db")


@pytest.fixture()
def test_engine(db_path):
    eng = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    return eng


@pytest.fixture()
def test_session_factory(test_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def patch_db(monkeypatch, db_path, test_engine, test_session_factory):
    """Redirect the whole app to use a temp DB for every test."""
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
    """TestClient whose dependency override yields from the temp DB."""
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


# ─── Clock tests ─────────────────────────────────────────────────────────────

def test_clock_real_mode():
    """In real mode, get_now() returns a timezone-aware UTC datetime close to now."""
    from app.core.clock import get_now, set_virtual_now
    set_virtual_now(None)
    now = get_now()
    assert now.tzinfo is not None, "get_now() must return a timezone-aware datetime"
    # Within 5 seconds of the real time
    real_now = datetime.now(timezone.utc)
    diff = abs((real_now - now).total_seconds())
    assert diff < 5.0, f"get_now() diverges from real time by {diff}s"


def test_clock_virtual_mode():
    """set_virtual_now() makes get_now() return the virtual time."""
    from app.core.clock import get_now, set_virtual_now
    fixed = datetime(2026, 11, 4, 10, 0, 0, tzinfo=timezone.utc)
    set_virtual_now(fixed)
    assert get_now() == fixed
    set_virtual_now(None)  # cleanup


def test_clock_resets_to_real():
    """After set_virtual_now(None), get_now() returns real time again."""
    from app.core.clock import get_now, set_virtual_now, is_scenario_mode
    set_virtual_now(datetime(2026, 11, 4, 10, 0, 0, tzinfo=timezone.utc))
    assert is_scenario_mode() is True
    set_virtual_now(None)
    assert is_scenario_mode() is False
    real_now = datetime.now(timezone.utc)
    diff = abs((real_now - get_now()).total_seconds())
    assert diff < 5.0


# ─── Anchor date tests ───────────────────────────────────────────────────────

def test_anchor_date_is_tuesday():
    """get_anchor_date() always returns a date whose weekday() == 1 (Tuesday)."""
    from app.services.campus.scenario import get_anchor_date
    import pytz

    tz = pytz.timezone("America/New_York")
    test_cases = [
        datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc),   # Monday
        datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc),   # Tuesday
        datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc),   # Wednesday
        datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc),   # Sunday
    ]
    scenario = {"id": "test"}
    for dt in test_cases:
        anchor = get_anchor_date(scenario, dt)
        assert anchor.weekday() == 1, (
            f"anchor_date for {dt.strftime('%A %Y-%m-%d')} should be Tuesday, "
            f"got {anchor.strftime('%A %Y-%m-%d')}"
        )


# ─── Scenario seeding tests ──────────────────────────────────────────────────

def test_scenario_seed_creates_commitments(client):
    """POST /sim/start seeds CalendarEvents from the scenario commitments."""
    r = client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "scenario"

    events = client.get("/api/v1/events").json()
    titles = [e["title"] for e in events]
    assert any("CSE 214" in t for t in titles), f"CSE 214 not in {titles}"
    assert any("MAT 203" in t for t in titles), f"MAT 203 not in {titles}"
    assert any("CSE 316" in t for t in titles), f"CSE 316 not in {titles}"

    # Clean up
    client.post("/api/v1/sim/stop")


def test_scenario_seed_creates_tasks(client):
    """POST /sim/start seeds tasks from the scenario."""
    r = client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    assert r.status_code == 200, r.text

    tasks = client.get("/api/v1/tasks").json()
    titles = [t["title"] for t in tasks]
    assert any("CSE 213" in t for t in titles), f"CSE 213 assignment not in {titles}"

    client.post("/api/v1/sim/stop")


def test_signals_applied_in_order(client):
    """Signals are applied in chronological order when advancing."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "09:15"})

    sigs = client.get("/api/v1/signals").json()
    applied_times = [s["at_utc"] for s in sigs if s["relevance"] == "relevant"]
    assert applied_times == sorted(applied_times), "Signals must be in chronological order"

    client.post("/api/v1/sim/stop")


def test_relevance_matches_oracle(client):
    """Filtered signal ids exactly equal expected_filtered_signals from the fixture."""
    fixture_path = (
        pathlib.Path(__file__).parent.parent.parent.parent
        / "aurora-campus-intelligence" / "sample-data" / "scenarios" / "demo_day.json"
    )
    fixture = json.loads(fixture_path.read_text())
    expected_filtered = set(fixture["expected_filtered_signals"])

    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "20:00"})

    sigs = client.get("/api/v1/signals").json()
    actual_filtered = {s["id"] for s in sigs if s["relevance"] == "filtered"}
    assert actual_filtered == expected_filtered, (
        f"Filtered signals mismatch.\n"
        f"  Expected: {sorted(expected_filtered)}\n"
        f"  Actual:   {sorted(actual_filtered)}"
    )

    client.post("/api/v1/sim/stop")


def test_advance_by_minutes(client):
    """POST /sim/advance with minutes advances the virtual clock correctly."""
    r = client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    start_vt = r.json()["virtual_now"]

    r2 = client.post("/api/v1/sim/advance", json={"minutes": 30})
    assert r2.status_code == 200, r2.text
    new_vt = r2.json()["virtual_now"]

    start_dt = datetime.fromisoformat(start_vt.replace("Z", "+00:00")) if start_vt else None
    new_dt = datetime.fromisoformat(new_vt.replace("Z", "+00:00")) if new_vt else None
    assert start_dt is not None and new_dt is not None
    delta = (new_dt - start_dt).total_seconds()
    assert abs(delta - 1800) < 5, f"Expected +30 min, got +{delta}s"

    client.post("/api/v1/sim/stop")


def test_advance_to_next_signal(client):
    """POST /sim/advance with to_next_signal=true advances past the next signal."""
    r_start = client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    assert r_start.status_code == 200
    start_vt = datetime.fromisoformat(r_start.json()["virtual_now"].replace("Z", "+00:00"))

    r_adv = client.post("/api/v1/sim/advance", json={"to_next_signal": True})
    assert r_adv.status_code == 200, r_adv.text
    new_vt = datetime.fromisoformat(r_adv.json()["virtual_now"].replace("Z", "+00:00"))
    assert new_vt > start_vt, "Virtual clock should advance past the next signal"

    client.post("/api/v1/sim/stop")


def test_room_change_mirrored(client):
    """After applying sig-005, CSE 214's location shows JAV-101 / Javits."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "09:15"})

    events = client.get("/api/v1/events").json()
    cse214 = next((e for e in events if "CSE 214" in e["title"]), None)
    assert cse214 is not None, f"CSE 214 not found in events: {[e['title'] for e in events]}"
    loc = cse214.get("location_text", "")
    assert "JAV" in loc or "Javits" in loc, (
        f"CSE 214 location should be Javits after sig-005, got: '{loc}'"
    )

    client.post("/api/v1/sim/stop")


def test_real_mode_unchanged(client):
    """Stopping scenario mode and calling /health works normally."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    r_stop = client.post("/api/v1/sim/stop")
    assert r_stop.status_code == 200
    assert r_stop.json()["mode"] == "real"

    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_feeds_status_returns_all_feeds(client):
    """GET /feeds/status returns entries for all 7 feeds after running the scenario."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "20:00"})

    feeds = client.get("/api/v1/feeds/status").json()
    feed_names = {f["feed"] for f in feeds}
    expected = {"solar", "brightspace", "campus_events", "shuttle", "weather", "building_ops", "library_rooms"}
    missing = expected - feed_names
    assert not missing, f"Missing feeds in /feeds/status: {missing}"

    client.post("/api/v1/sim/stop")

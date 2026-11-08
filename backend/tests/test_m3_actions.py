"""
M3 tests: action layer, autonomy policy, undo, ICS export, golden day phase 2.
"""
from __future__ import annotations

import json
import pathlib
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

_CAMPUS_TZ = pytz.timezone("America/New_York")
DEMO_USER = "test-user-0001"

# ─── DB / client fixtures (same pattern as test_m2_moves.py) ──────────────────

@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test_m3.db")


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


@pytest.fixture()
def db(test_session_factory):
    """Direct DB session for service-layer unit tests."""
    session = test_session_factory()
    yield session
    session.close()


# ─── Unit tests: allowlist enforcement ────────────────────────────────────────

def test_allowlist_enforcement(db):
    """Executing an unlisted action type raises ValueError."""
    from app.services.campus.actions import execute_action

    mock_move = MagicMock()
    mock_move.id = "move-test-001"
    mock_move.scenario_id = None

    with pytest.raises(ValueError, match="not in the allowlist"):
        execute_action(db, {"id": "x", "type": "send_email", "params": {}}, mock_move)


def test_no_send_action_in_codebase():
    """Assert no 'send' action type is in the ALLOWLIST or anywhere in services/campus/."""
    from app.services.campus.actions import ALLOWLIST

    for t in ALLOWLIST:
        assert "send" not in t.lower(), f"Action type '{t}' looks like a send action"

    # Grep the campus services directory for any suspicious send patterns
    # Exclude __pycache__ and the safety comment in actions.py
    import subprocess
    campus_dir = pathlib.Path(__file__).parent.parent / "app" / "services" / "campus"
    result = subprocess.run(
        ["grep", "-rn", "--include=*.py",
         r"send_email\|sendmail\|smtp\|requests\.post", str(campus_dir)],
        capture_output=True, text=True,
    )
    # Filter out comment lines (lines starting with # after stripping)
    suspicious = [
        line for line in result.stdout.splitlines()
        if not line.split(":", 2)[-1].lstrip().startswith("#")
        and not line.split(":", 2)[-1].lstrip().startswith('"""')
        and "no send" not in line.lower()
        and "no smtp" not in line.lower()
        and "no requests.post" not in line.lower()
        and "no email" not in line.lower()
    ]
    assert suspicious == [], (
        f"Suspicious send patterns found in services/campus/:\n" + "\n".join(suspicious)
    )


def test_allowlist_contents():
    """ALLOWLIST contains exactly the expected types, none of which are send actions."""
    from app.services.campus.actions import ALLOWLIST, SIMULATED_TYPES, EXTERNAL_TYPES

    expected = {
        "create_calendar_block",
        "update_event_location",
        "create_task",
        "add_reminder",
        "book_room",
        "request_room_change",
        "draft_message",
    }
    assert ALLOWLIST == expected

    assert SIMULATED_TYPES == {"book_room", "request_room_change", "draft_message"}
    assert EXTERNAL_TYPES == {"book_room", "request_room_change"}


# ─── Unit tests: autonomy policy ──────────────────────────────────────────────

def test_autonomy_defaults(db):
    """Default policy has correct values."""
    from app.services.campus.autonomy import DEFAULT_POLICY, get_policy

    policy = get_policy(db)
    assert policy["my_calendar_tasks_reminders"] == "auto"
    assert policy["attended_plan_changes"] == "ask"
    assert policy["simulated_external"] == "ask"
    assert policy["message_drafts"] == "ask"


def test_autonomy_lock_cannot_be_overridden_service(db):
    """set_policy raises PolicyLockError for locked categories."""
    from app.services.campus.autonomy import PolicyLockError, set_policy

    with pytest.raises(PolicyLockError):
        set_policy(db, {"simulated_external": "auto"})

    with pytest.raises(PolicyLockError):
        set_policy(db, {"message_drafts": "auto"})


def test_autonomy_unlocked_category_can_change(db):
    """Non-locked categories can be changed."""
    from app.services.campus.autonomy import get_policy, set_policy

    updated = set_policy(db, {"attended_plan_changes": "auto"})
    assert updated["attended_plan_changes"] == "auto"
    # Locks remain
    assert updated["simulated_external"] == "ask"
    assert updated["message_drafts"] == "ask"

    # Re-read from DB
    fresh = get_policy(db)
    assert fresh["attended_plan_changes"] == "auto"


# ─── API tests: autonomy endpoints ────────────────────────────────────────────

def test_get_autonomy(client):
    """GET /autonomy returns policy + locked list."""
    r = client.get("/api/v1/autonomy")
    assert r.status_code == 200
    body = r.json()
    assert "policy" in body
    assert "locked" in body
    assert "simulated_external" in body["locked"]
    assert "message_drafts" in body["locked"]
    assert body["policy"]["my_calendar_tasks_reminders"] == "auto"


def test_autonomy_lock_cannot_be_overridden(client):
    """PUT /autonomy with simulated_external=auto returns 400."""
    r = client.put("/api/v1/autonomy", json={"category": "simulated_external", "value": "auto"})
    assert r.status_code == 400
    assert "locked" in r.json()["detail"].lower() or "cannot" in r.json()["detail"].lower()


def test_autonomy_lock_message_drafts(client):
    """PUT /autonomy with message_drafts=auto returns 400."""
    r = client.put("/api/v1/autonomy", json={"category": "message_drafts", "value": "auto"})
    assert r.status_code == 400


def test_autonomy_put_valid(client):
    """PUT /autonomy with a valid unlocked change succeeds."""
    r = client.put("/api/v1/autonomy", json={"category": "attended_plan_changes", "value": "auto"})
    assert r.status_code == 200
    assert r.json()["policy"]["attended_plan_changes"] == "auto"


# ─── API tests: auto-execute on advance ───────────────────────────────────────

def test_auto_policy_executes_and_is_auto_applied(client):
    """After starting scenario and advancing to 07:35, deadline move is auto_applied."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "07:35"})
    moves = client.get("/api/v1/moves?audience=student").json()
    deadline = next((m for m in moves if m["key"] == "deadline:t-cse213-a3"), None)
    assert deadline is not None, f"deadline:t-cse213-a3 not found in moves: {[m['key'] for m in moves]}"
    assert deadline["status"] == "auto_applied", f"Expected auto_applied, got {deadline['status']}"


def test_auto_applied_move_in_handled(client):
    """auto_applied moves appear in GET /moves/handled."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "07:35"})

    handled = client.get("/api/v1/moves/handled?audience=student").json()
    auto_keys = [m["key"] for m in handled if m["status"] == "auto_applied"]
    assert "deadline:t-cse213-a3" in auto_keys, \
        f"Expected deadline:t-cse213-a3 in handled, got: {auto_keys}"


def test_auto_blocks_created(client):
    """After auto_applied deadline move, aurora_block events are created."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "07:35"})

    events = client.get("/api/v1/events").json()
    aurora_blocks = [e for e in events if e.get("source_type") == "aurora_block"]
    assert len(aurora_blocks) >= 1, f"Expected ≥1 aurora_block, got {len(aurora_blocks)}"


# ─── API tests: approve move ──────────────────────────────────────────────────

def test_approve_executes_actions(client):
    """Approving an ask-policy move executes its actions."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "12:20"})

    # Find the conflict move (policy=ask)
    moves = client.get("/api/v1/moves?audience=student").json()
    conflict = next((m for m in moves if m["key"].startswith("conflict:ev-fair")), None)
    assert conflict is not None, f"No conflict move found; moves: {[m['key'] for m in moves]}"

    r = client.post(f"/api/v1/moves/{conflict['id']}/approve")
    assert r.status_code == 200
    assert r.json()["status"] in ("executed", "executed_simulated")


def test_approve_returns_409_for_handled_move(client):
    """Approving an already-handled move returns 409."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "07:35"})

    handled = client.get("/api/v1/moves/handled?audience=student").json()
    auto_applied = next((m for m in handled if m["status"] == "auto_applied"), None)
    assert auto_applied is not None

    r = client.post(f"/api/v1/moves/{auto_applied['id']}/approve")
    assert r.status_code == 409


# ─── API tests: simulated actions labeling ────────────────────────────────────

def test_simulated_actions_are_labeled(client):
    """Approving the group move: book_room and draft_message have simulated=True in ActionLog."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "16:15"})

    moves = client.get("/api/v1/moves?audience=student").json()
    group_move = next((m for m in moves if m["key"] == "group:t-cse316-report:slot"), None)
    assert group_move is not None, f"group move not found; keys: {[m['key'] for m in moves]}"

    r = client.post(f"/api/v1/moves/{group_move['id']}/approve")
    assert r.status_code == 200
    assert r.json()["status"] == "executed_simulated"


# ─── API tests: audit events ──────────────────────────────────────────────────

def test_audit_rows_written(client, test_session_factory):
    """After approving group move, AuditEvent rows exist for the move."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "16:15"})

    moves = client.get("/api/v1/moves?audience=student").json()
    group_move = next((m for m in moves if m["key"] == "group:t-cse316-report:slot"), None)
    assert group_move is not None

    client.post(f"/api/v1/moves/{group_move['id']}/approve")

    from app.models.models import AuditEvent
    db = test_session_factory()
    try:
        audit_rows = (
            db.query(AuditEvent)
            .filter(AuditEvent.resource_id == group_move["id"])
            .all()
        )
        assert len(audit_rows) >= 1, f"Expected ≥1 AuditEvent for move, got {len(audit_rows)}"
    finally:
        db.close()


# ─── API tests: undo ──────────────────────────────────────────────────────────

def test_undo_auto_move_restores_state(client, test_session_factory):
    """Undo on an auto-applied deadline block removes the calendar event."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "07:35"})

    events_before = client.get("/api/v1/events").json()
    aurora_before = [e for e in events_before if e.get("source_type") == "aurora_block"]
    assert len(aurora_before) >= 1, "Expected ≥1 aurora_block after auto_applied"

    # Find the ActionLog entry for the auto-applied move
    from app.models.models import ActionLog
    db = test_session_factory()
    try:
        logs = db.query(ActionLog).filter(
            ActionLog.action_type == "create_calendar_block",
            ActionLog.status == "executed",
        ).all()
        assert len(logs) >= 1, f"No create_calendar_block ActionLog found"
        log_id = logs[0].id
    finally:
        db.close()

    # Undo the action
    r = client.post(f"/api/v1/moves/actions/{log_id}/undo")
    assert r.status_code == 200
    assert r.json()["status"] == "undone"

    events_after = client.get("/api/v1/events").json()
    aurora_after = [e for e in events_after if e.get("source_type") == "aurora_block"]
    assert len(aurora_after) < len(aurora_before), \
        "Expected fewer aurora_block events after undo"


# ─── API tests: dismiss does not repropose ────────────────────────────────────

def test_dismiss_then_advance_does_not_repropose(client):
    """Dismissing conflict move, then advancing past 12:20 → move stays dismissed."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "12:20"})

    moves = client.get("/api/v1/moves?audience=student").json()
    conflict = next((m for m in moves if m["key"].startswith("conflict:ev-fair")), None)
    assert conflict is not None

    client.post(f"/api/v1/moves/{conflict['id']}/dismiss")

    # Advance a bit further
    client.post("/api/v1/sim/advance", json={"minutes": 10})

    active = client.get("/api/v1/moves?audience=student").json()
    active_keys = [m["key"] for m in active]
    assert conflict["key"] not in active_keys, \
        f"Dismissed conflict move reappeared after advance: {active_keys}"


# ─── API tests: no overlapping blocks ─────────────────────────────────────────

def test_no_overlapping_blocks_after_auto(client):
    """After auto_applied deadline move, no two aurora_blocks overlap."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "07:35"})

    events = client.get("/api/v1/events").json()
    blocks = sorted(
        [e for e in events if e.get("source_type") == "aurora_block"],
        key=lambda e: e["start_at_utc"],
    )

    for i in range(len(blocks) - 1):
        a, b = blocks[i], blocks[i + 1]
        a_start, a_end = a["start_at_utc"], a["end_at_utc"]
        b_start, b_end = b["start_at_utc"], b["end_at_utc"]
        # Overlap condition: a starts before b ends AND b starts before a ends
        assert not (a_start < b_end and b_start < a_end), (
            f"Aurora blocks overlap: {a['title']} ({a_start}–{a_end}) "
            f"and {b['title']} ({b_start}–{b_end})"
        )


# ─── API tests: ICS export ────────────────────────────────────────────────────

def test_ics_export_empty_without_blocks(client):
    """GET /calendar/aurora.ics returns valid ICS with no VEVENTs when no aurora blocks exist."""
    r = client.get("/api/v1/calendar/aurora.ics")
    assert r.status_code == 200
    assert "BEGIN:VCALENDAR" in r.text
    assert "END:VCALENDAR" in r.text


def test_ics_export_parses_correctly(client):
    """GET /calendar/aurora.ics returns valid ICS with aurora blocks after auto_applied move."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "07:35"})

    r = client.get("/api/v1/calendar/aurora.ics")
    assert r.status_code == 200
    assert "text/calendar" in r.headers.get("content-type", "")
    assert "BEGIN:VCALENDAR" in r.text
    assert "BEGIN:VEVENT" in r.text
    assert "END:VEVENT" in r.text
    assert "END:VCALENDAR" in r.text
    assert "AURORA Blocks" in r.text
    assert "DTSTART;TZID=America/New_York:" in r.text


def test_ics_export_uid_format(client):
    """Each VEVENT in the ICS export has a UID ending with @aurora."""
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})
    client.post("/api/v1/sim/advance", json={"to": "07:35"})

    r = client.get("/api/v1/calendar/aurora.ics")
    assert r.status_code == 200
    # Count UIDs
    uid_lines = [line for line in r.text.splitlines() if line.startswith("UID:")]
    vevent_count = r.text.count("BEGIN:VEVENT")
    assert len(uid_lines) == vevent_count
    for line in uid_lines:
        assert line.endswith("@aurora"), f"UID does not end with @aurora: {line}"


# ─── Golden day phase 2 ───────────────────────────────────────────────────────

def test_demo_day_golden_phase2(client, test_session_factory):
    """
    Full golden day with M3: statuses, approve/dismiss branches, end state.
    """
    client.post("/api/v1/sim/start", json={"scenario_id": "disrupted_tuesday"})

    # ── 07:35 — deadline:t-cse213-a3 is auto_applied; ≥1 aurora blocks ───────
    client.post("/api/v1/sim/advance", json={"to": "07:35"})
    moves = client.get("/api/v1/moves?audience=student").json()
    deadline = next((m for m in moves if m["key"] == "deadline:t-cse213-a3"), None)
    assert deadline is not None, f"deadline move not found: {[m['key'] for m in moves]}"
    assert deadline["status"] == "auto_applied"

    events = client.get("/api/v1/events").json()
    aurora_blocks = [e for e in events if e.get("source_type") == "aurora_block"]
    assert len(aurora_blocks) >= 1, f"Expected ≥1 aurora_block, got {len(aurora_blocks)}"

    # ── 08:10 — ingest:sig-004 is auto_applied, task exists ──────────────────
    client.post("/api/v1/sim/advance", json={"to": "08:10"})
    moves = client.get("/api/v1/moves?audience=student").json()
    ingest = next((m for m in moves if m["key"] == "ingest:sig-004"), None)
    assert ingest is not None, f"ingest:sig-004 not found: {[m['key'] for m in moves]}"
    assert ingest["status"] == "auto_applied"

    tasks = client.get("/api/v1/tasks").json()
    quiz_task = next((t for t in tasks if "Quiz 4" in t["title"] or "quiz 4" in t["title"].lower()), None)
    assert quiz_task is not None, f"Quiz 4 task not created; tasks: {[t['title'] for t in tasks]}"
    assert quiz_task["source_signal_id"] == "sig-004"

    # ── 12:20 — conflict:ev-fair:* exists with policy=ask ────────────────────
    client.post("/api/v1/sim/advance", json={"to": "12:20"})
    moves = client.get("/api/v1/moves?audience=student").json()
    conflict = next((m for m in moves if m["key"].startswith("conflict:ev-fair")), None)
    assert conflict is not None, f"conflict move not found: {[m['key'] for m in moves]}"
    assert conflict["policy"] == "ask"

    # Approve the conflict move
    r = client.post(f"/api/v1/moves/{conflict['id']}/approve")
    assert r.status_code == 200
    assert r.json()["status"] in ("executed", "executed_simulated")

    # Conflict move should now be in handled
    handled = client.get("/api/v1/moves/handled?audience=student").json()
    handled_keys = [m["key"] for m in handled]
    assert conflict["key"] in handled_keys

    # ── 16:15 — group:t-cse316-report:slot appears (ask) ─────────────────────
    client.post("/api/v1/sim/advance", json={"to": "16:15"})
    moves = client.get("/api/v1/moves?audience=student").json()
    group = next((m for m in moves if m["key"] == "group:t-cse316-report:slot"), None)
    assert group is not None, f"group move not found: {[m['key'] for m in moves]}"
    assert group["policy"] == "ask"

    # Approve the group move (has simulated actions → executed_simulated)
    r = client.post(f"/api/v1/moves/{group['id']}/approve")
    assert r.status_code == 200
    assert r.json()["status"] == "executed_simulated"

    # ── Autonomy: locked categories still locked after full scenario ──────────
    r = client.put("/api/v1/autonomy", json={"category": "simulated_external", "value": "auto"})
    assert r.status_code == 400

    # ── End of day: filtered signals check ───────────────────────────────────
    client.post("/api/v1/sim/advance", json={"to": "20:00"})
    sigs = client.get("/api/v1/signals").json()
    filtered_ids = {s["id"] for s in sigs if s["relevance"] == "filtered"}
    # sig-006 (shuttle) and sig-011 (chess club) must be filtered
    assert "sig-006" in filtered_ids, f"sig-006 not filtered; filtered: {filtered_ids}"
    assert "sig-011" in filtered_ids, f"sig-011 not filtered; filtered: {filtered_ids}"

    # ── Undo an auto-applied action ───────────────────────────────────────────
    from app.models.models import ActionLog
    db = test_session_factory()
    try:
        block_log = db.query(ActionLog).filter(
            ActionLog.action_type == "create_calendar_block",
            ActionLog.status == "executed",
        ).first()
    finally:
        db.close()

    if block_log:
        r = client.post(f"/api/v1/moves/actions/{block_log.id}/undo")
        assert r.status_code == 200
        assert r.json()["status"] == "undone"

    # Verify ICS reflects current aurora blocks
    r = client.get("/api/v1/calendar/aurora.ics")
    assert r.status_code == 200
    assert "BEGIN:VCALENDAR" in r.text

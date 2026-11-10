"""
Scenario loader and seed manager.

Reads a JSON fixture from sample-data/scenarios/<id>.json and seeds the demo
user's calendar events, tasks, and announcements relative to the anchor date.

The anchor date is the next Tuesday on or after *now* in America/New_York.

NEVER reads the fixture's 'relevant' field in production code.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pytz
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import (
    Announcement,
    CalendarEvent,
    SimState,
    Task,
)

# Fixtures live two levels above the backend package
_SCENARIOS_DIR = (
    Path(__file__).parent.parent.parent.parent.parent / "sample-data" / "scenarios"
)
_CAMPUS_TZ = pytz.timezone("America/New_York")


# ─── Anchor date ──────────────────────────────────────────────────────────────

def get_anchor_date(scenario: dict, now: datetime) -> date:
    """Return the next Tuesday on or after *now* in campus timezone."""
    local_now = now.astimezone(_CAMPUS_TZ).date()
    days_ahead = (1 - local_now.weekday()) % 7  # 1 = Tuesday
    return local_now + timedelta(days=days_ahead)


# ─── Time helpers ─────────────────────────────────────────────────────────────

def _local_hhmm_to_utc(anchor: date, hhmm: str, day_offset: int = 0) -> datetime:
    """Convert 'HH:MM' on anchor+day_offset in campus time to UTC datetime."""
    h, m = map(int, hhmm.split(":"))
    target = anchor + timedelta(days=day_offset)
    local_dt = _CAMPUS_TZ.localize(datetime(target.year, target.month, target.day, h, m))
    return local_dt.astimezone(timezone.utc)


# ─── Load ─────────────────────────────────────────────────────────────────────

def load_scenario(scenario_id: str) -> dict:
    """Read and parse the JSON fixture from sample-data/scenarios/<id>.json."""
    path = _SCENARIOS_DIR / f"{scenario_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Scenario fixture not found: {path}")
    return json.loads(path.read_text())


# ─── Seed ─────────────────────────────────────────────────────────────────────

def seed_scenario(db: Session, scenario: dict, anchor: date) -> None:
    """
    Clear existing scenario-tagged rows for the demo user, then seed fresh rows
    from the fixture relative to *anchor*.

    Sources:
      - commitments  → CalendarEvent (source_type='scenario')
      - saved_events → CalendarEvent (source_type='scenario')
      - tasks        → Task (provenance='scenario')
    """
    user_id = settings.demo_user_id
    scenario_id = scenario["id"]

    # Clear old scenario data
    reset_scenario(db)

    # ── Seed class commitments ─────────────────────────────────────────────
    for c in scenario.get("commitments", []):
        start_utc = _local_hhmm_to_utc(anchor, c["start"])
        end_utc = _local_hhmm_to_utc(anchor, c["end"])
        event = CalendarEvent(
            user_id=user_id,
            title=c["title"],
            description=f"Course: {c.get('course', '')}",
            start_at_utc=start_utc,
            end_at_utc=end_utc,
            location_text=c.get("room"),
            event_type="class",
            source_type="scenario",
            source_reference=c["id"],  # commitment id for signal matching
        )
        db.add(event)

    # ── Seed saved events ──────────────────────────────────────────────────
    for ev in scenario.get("saved_events", []):
        when = ev.get("when", {})
        day_offset = when.get("day_offset", 0)
        start_utc = _local_hhmm_to_utc(anchor, when["start"], day_offset)
        end_utc = _local_hhmm_to_utc(anchor, when["end"], day_offset)
        event = CalendarEvent(
            user_id=user_id,
            title=ev["title"],
            start_at_utc=start_utc,
            end_at_utc=end_utc,
            location_text=ev.get("room"),
            event_type="other",
            source_type="scenario",
            source_reference=ev["id"],  # event id for signal matching
        )
        db.add(event)

    # ── Seed tasks ─────────────────────────────────────────────────────────
    for t in scenario.get("tasks", []):
        due = t.get("due", {})
        day_offset = due.get("day_offset", 0)
        due_utc = _local_hhmm_to_utc(anchor, due["time"], day_offset) if due else None
        task = Task(
            id=t["id"],           # preserve fixture ID so detector keys are stable
            user_id=user_id,
            title=t["title"],
            course_label=t.get("course"),
            due_at_utc=due_utc,
            estimated_minutes=t.get("est_minutes", 30),
            priority="normal",
            status="todo",
            source_type="approved_connector",  # distinguish from legacy 'demo' tasks (D1)
            source_signal_id=None,
            provenance="scenario",
        )
        db.add(task)

    db.commit()


# ─── Reset ────────────────────────────────────────────────────────────────────

def reset_scenario(db: Session) -> None:
    """Delete all rows tagged with scenario provenance for the demo user.

    D3 fix: also delete aurora_block CalendarEvents so repeated starts
    don't accumulate extra blocks.

    D1 fix: legacy demo tasks (source_type='demo') are filtered out in
    world.py when a scenario is active (filtered by provenance/source_type),
    so they do not need to be deleted or modified here.
    """
    from app.models.models import Move, Signal  # avoid circular at module level

    user_id = settings.demo_user_id

    # Delete scenario-seeded class/saved events
    db.query(CalendarEvent).filter(
        CalendarEvent.user_id == user_id,
        CalendarEvent.source_type == "scenario",
    ).delete(synchronize_session=False)

    # D3: delete aurora_blocks created by previous scenario runs
    db.query(CalendarEvent).filter(
        CalendarEvent.user_id == user_id,
        CalendarEvent.source_type == "aurora_block",
    ).delete(synchronize_session=False)

    # Delete scenario-seeded tasks (D1: these now use source_type='approved_connector'
    # with provenance='scenario' to distinguish them from legacy demo tasks)
    db.query(Task).filter(
        Task.user_id == user_id,
        Task.provenance == "scenario",
    ).delete(synchronize_session=False)

    db.query(Announcement).filter(
        Announcement.user_id == user_id,
        Announcement.source_type == "demo",
        # We tag scenario announcements with source_url='scenario'
        Announcement.source_url == "scenario",
    ).delete(synchronize_session=False)

    db.query(Signal).delete(synchronize_session=False)
    db.query(Move).delete(synchronize_session=False)

    db.commit()


# ─── SimState helpers ─────────────────────────────────────────────────────────

def get_or_create_sim_state(db: Session) -> SimState:
    """Return the single SimState row; create with defaults if absent."""
    state = db.get(SimState, 1)
    if state is None:
        state = SimState(id=1)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state

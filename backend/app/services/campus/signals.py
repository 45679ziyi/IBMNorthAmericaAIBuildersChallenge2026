"""
Feed adapter protocol and signal application.

FeedAdapter protocol:
    name: str
    def poll(self, since: datetime, until: datetime) -> list[Signal]: ...

    Real connector requirements (not implemented):
    - Written authorization from the data owner
    - OAuth 2.0 credentials or API key with least-privilege scope
    - Rate limit compliance (back off on 429)
    - Incremental sync (since/until parameters, cursor-based)
    - TLS 1.2+ for all requests
    This prototype uses FixtureFeed only.

NEVER reads the scenario fixture's 'relevant' field in production code.
Relevance is computed by compute_relevance() from the persona and the world.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Protocol, runtime_checkable

import pytz
from sqlalchemy.orm import Session

from app.models.models import (
    Announcement,
    CalendarEvent,
    Signal,
    SimState,
)
from app.core.config import settings

_CAMPUS_TZ = pytz.timezone("America/New_York")


# ─── Protocol ─────────────────────────────────────────────────────────────────

@runtime_checkable
class FeedAdapter(Protocol):
    name: str

    def poll(self, since: datetime, until: datetime) -> list[Signal]:
        ...


# ─── Relevance ────────────────────────────────────────────────────────────────

def compute_relevance(
    signal: Signal,
    persona: dict,
    world_snapshot: dict,
) -> tuple[str, str]:
    """
    Compute (relevance, reason) for a signal given the persona and world state.

    Rules:
    - shuttle / delay kind → filtered if persona does not use the shuttle.
    - campus_events / event_announced kind → filtered if the event title is not
      in the student's saved event titles.
    - weather / forecast_change → relevant (M1 placeholder; walk-check in M2).
    - Everything else → relevant.

    Never reads signal.payload['relevant'] or any fixture 'relevant' field.
    """
    feed = signal.feed
    kind = signal.kind

    # ── Shuttle delay ──────────────────────────────────────────────────────
    if feed == "shuttle":
        if not persona.get("uses_shuttle", True):
            return "filtered", "Shuttle delay: persona does not use the shuttle"

    # ── Campus events not saved by student ────────────────────────────────
    if kind == "event_announced":
        saved_titles: list[str] = [
            t.lower() for t in world_snapshot.get("saved_event_titles", [])
        ]
        try:
            payload = json.loads(signal.payload) if isinstance(signal.payload, str) else signal.payload
        except (json.JSONDecodeError, TypeError):
            payload = {}
        event_title = payload.get("title", "").lower()
        if not any(event_title in saved or saved in event_title for saved in saved_titles):
            return "filtered", "Event not saved by student"

    # ── Weather ───────────────────────────────────────────────────────────
    if feed == "weather":
        # M1: always relevant; M2 will check the walk matrix
        return "relevant", "Weather in outdoor walk window."

    return "relevant", ""


# ─── FixtureFeed ──────────────────────────────────────────────────────────────

class FixtureFeed:
    """Feed adapter backed by a scenario fixture (offline, synthetic only)."""

    def __init__(self, scenario: dict, anchor: date) -> None:
        self.name: str = "fixture"
        self._scenario = scenario
        self._anchor = anchor

    def poll(self, since: datetime, until: datetime) -> list[Signal]:
        """
        Return Signal ORM objects whose virtual time falls in [since, until).
        Times are parsed as HH:MM on the anchor date in campus time → UTC.
        Never reads the 'relevant' field from the fixture.
        """
        results: list[Signal] = []
        scenario_id = self._scenario.get("id", "unknown")

        for entry in self._scenario.get("timeline", []):
            at_utc = _hhmm_to_utc(self._anchor, entry["at"])
            if since <= at_utc < until:
                payload_raw = entry.get("payload", {})
                signal = Signal(
                    id=entry["id"],
                    feed=entry["feed"],
                    kind=entry["kind"],
                    at_utc=at_utc,
                    summary=entry["summary"],
                    payload=json.dumps(payload_raw),
                    relevance="relevant",       # will be computed later
                    relevance_reason=None,
                    data_origin="synthetic",
                    scenario_id=scenario_id,
                )
                results.append(signal)

        return results


# ─── Time helper ──────────────────────────────────────────────────────────────

def _hhmm_to_utc(anchor: date, hhmm: str, day_offset: int = 0) -> datetime:
    h, m = map(int, hhmm.split(":"))
    target = anchor + timedelta(days=day_offset)
    local_dt = _CAMPUS_TZ.localize(datetime(target.year, target.month, target.day, h, m))
    return local_dt.astimezone(timezone.utc)


# ─── Apply signal ─────────────────────────────────────────────────────────────

def apply_signal(
    db: Session,
    signal: Signal,
    scenario: dict,
    anchor: date,
    sim_state: SimState,
) -> None:
    """
    Mirror a signal's effect into the world (DB state), then mark it applied.

    Effects:
    - room_change         : update CalendarEvent.location_text by commitment id
    - event_rescheduled   : update CalendarEvent start/end times by event id
    - announcement        : insert Announcement row
    - schedule_snapshot, deadlines_snapshot, saved_events_snapshot: no-op
    - All others          : no-op for M1
    """
    user_id = settings.demo_user_id

    try:
        payload = json.loads(signal.payload) if isinstance(signal.payload, str) else signal.payload
    except (json.JSONDecodeError, TypeError):
        payload = {}

    if signal.kind == "room_change":
        commitment_id = payload.get("commitment")
        new_room_id = payload.get("to")
        if commitment_id and new_room_id:
            # Map room id to a human-readable name from the rooms list
            room_name = _room_id_to_name(scenario, new_room_id)
            event = (
                db.query(CalendarEvent)
                .filter(
                    CalendarEvent.user_id == user_id,
                    CalendarEvent.source_reference == commitment_id,
                )
                .first()
            )
            if event:
                event.location_text = room_name or new_room_id

    elif signal.kind == "event_rescheduled":
        event_id = payload.get("event")
        to = payload.get("to", {})
        if event_id and to:
            day_offset = to.get("day_offset", 0)
            new_start = _hhmm_to_utc(anchor, to["start"], day_offset)
            new_end = _hhmm_to_utc(anchor, to["end"], day_offset)
            event = (
                db.query(CalendarEvent)
                .filter(
                    CalendarEvent.user_id == user_id,
                    CalendarEvent.source_reference == event_id,
                )
                .first()
            )
            if event:
                event.start_at_utc = new_start
                event.end_at_utc = new_end

    elif signal.kind == "announcement":
        ann = Announcement(
            user_id=user_id,
            course_label=payload.get("course", ""),
            title=payload.get("title", signal.summary),
            body_summary=payload.get("body", signal.summary),
            published_at_utc=signal.at_utc,
            source_type="demo",
            source_url="scenario",   # sentinel for cleanup
            is_read=False,
        )
        db.add(ann)

    # schedule_snapshot, deadlines_snapshot, saved_events_snapshot,
    # incident, delay, forecast_change, availability, event_announced
    # → no-op for M1 (handled by seed or M2 engine)

    # Mark applied in sim_state
    applied = json.loads(sim_state.applied_signal_ids)
    if signal.id not in applied:
        applied.append(signal.id)
    sim_state.applied_signal_ids = json.dumps(applied)

    db.commit()


# ─── World snapshot ───────────────────────────────────────────────────────────

def build_world_snapshot(db: Session, scenario: dict) -> dict:
    """
    Build a minimal world snapshot for relevance computation.
    Currently tracks saved event titles.
    """
    user_id = settings.demo_user_id
    saved_titles = [
        ev["title"] for ev in scenario.get("saved_events", [])
    ]
    return {"saved_event_titles": saved_titles}


# ─── Feed status ──────────────────────────────────────────────────────────────

def get_feed_statuses(db: Session) -> list[dict]:
    """Return aggregated per-feed status from the signals table."""
    from sqlalchemy import func

    signals = db.query(Signal).all()
    feeds: dict[str, dict] = {}
    for sig in signals:
        if sig.feed not in feeds:
            feeds[sig.feed] = {
                "feed": sig.feed,
                "last_signal_at": None,
                "signals_seen": 0,
                "signals_filtered": 0,
            }
        entry = feeds[sig.feed]
        entry["signals_seen"] += 1
        if sig.relevance == "filtered":
            entry["signals_filtered"] += 1
        if entry["last_signal_at"] is None or sig.at_utc > entry["last_signal_at"]:
            entry["last_signal_at"] = sig.at_utc

    return list(feeds.values())


# ─── Room helper ──────────────────────────────────────────────────────────────

def _room_id_to_name(scenario: dict, room_id: str) -> str | None:
    for r in scenario.get("rooms", []):
        if r["id"] == room_id:
            return r.get("name", room_id)
    return room_id

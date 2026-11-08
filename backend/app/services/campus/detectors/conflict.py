"""
Detector: conflict

Trigger: a saved event that now overlaps a class or accepted aurora_block.
Computes an attendance window (if ≥ 30 min).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytz

from app.services.campus.detectors.base import MoveSpec
from app.services.campus.world import World, _round_up_5, _round_down_5

_CAMPUS_TZ = pytz.timezone("America/New_York")
_MIN_WINDOW = 30  # minutes


def _loc(anchor, h: int, m: int) -> datetime:
    return _CAMPUS_TZ.localize(datetime(anchor.year, anchor.month, anchor.day, h, m))


def _loc_t(anchor, t) -> datetime:
    return _loc(anchor, t.hour, t.minute)


def detect(world: World, now: datetime) -> list[MoveSpec]:
    """
    For each saved event on the anchor date, check if it overlaps a commitment.
    If so, compute attendance window = [max(event_start, prev_end+walk), next_start−walk−buffer].
    """
    results: list[MoveSpec] = []

    if now.tzinfo is None:
        now = now.replace(tzinfo=pytz.utc)

    persona = world.scenario.get("persona", {})
    start_place = persona.get("start_place", "MEL")

    # Active rain windows (for notes in why)
    rain_windows: list[tuple[datetime, datetime]] = _rain_windows(world)

    for ev in world.saved_events:
        ev_start = ev.start_at_utc
        ev_end = ev.end_at_utc
        if ev_start is None or ev_end is None:
            continue

        # Normalize to timezone-aware
        if ev_start.tzinfo is None:
            ev_start = ev_start.replace(tzinfo=pytz.utc)
        if ev_end.tzinfo is None:
            ev_end = ev_end.replace(tzinfo=pytz.utc)

        # Convert to campus-local for date comparison
        ev_start_local = ev_start.astimezone(_CAMPUS_TZ)
        ev_end_local = ev_end.astimezone(_CAMPUS_TZ)

        # Only process events on anchor date
        if ev_start_local.date() != world.anchor_date:
            continue

        # Find overlapping commitments
        overlapping = _find_overlapping_commitments(world, ev_start, ev_end)
        if not overlapping:
            continue

        # Determine the event's room/building
        ev_room_id = _resolve_room_id(ev.location_text or "", world.rooms)
        ev_building = _building_from_room(ev_room_id, world.rooms)

        # For each overlapping commitment, compute the conflict window
        for commitment in overlapping:
            commitment_start = _loc_t(world.anchor_date, commitment.start)
            commitment_end = _loc_t(world.anchor_date, commitment.end)

            # Previous commitment before the event window
            prev_commitment = _prev_commitment(world, ev_start_local)
            if prev_commitment:
                prev_end = _loc_t(world.anchor_date, prev_commitment.end)
                walk_to_event = world.walk_minutes(prev_commitment.building_id, ev_building)
                earliest_arrival = prev_end + timedelta(minutes=walk_to_event)
            else:
                # Use start_place
                walk_to_event = world.walk_minutes(start_place, ev_building)
                earliest_arrival = ev_start + timedelta(minutes=walk_to_event)
                # Clamp to ev_start
                earliest_arrival = min(earliest_arrival, ev_start)

            # Attendance window start = max(ev_start, earliest_arrival)
            window_start = max(ev_start.astimezone(_CAMPUS_TZ), earliest_arrival.astimezone(_CAMPUS_TZ))
            window_start = _round_up_5(window_start)

            # Walk from event to next class
            walk_to_class = world.walk_minutes(ev_building, commitment.building_id)
            # Window end = next_class_start − walk − buffer
            window_end_raw = commitment_start - timedelta(minutes=walk_to_class + world.walking_buffer)
            window_end = _round_down_5(window_end_raw)

            duration_min = (window_end - window_start).total_seconds() / 60

            key = f"conflict:{ev.source_reference or ev.id}:{commitment.id}"

            # Rain note if walk overlaps rain window
            rain_note = ""
            if rain_windows:
                walk_during_rain = any(
                    _overlaps(commitment_start - timedelta(minutes=walk_to_class), commitment_start, rs, re)
                    for rs, re in rain_windows
                )
                if walk_during_rain:
                    rain_note = " (walk to class is in rain window)"

            ev_ref = ev.source_reference or ev.id
            ev_title = ev.title

            if duration_min < _MIN_WINDOW:
                results.append(MoveSpec(
                    key=key,
                    kind="conflict",
                    audience="student",
                    policy="info",
                    urgency="today",
                    impact="low",
                    title=f"Attendance window too short: {ev_title}",
                    summary=(
                        f"{ev_title} overlaps {commitment.title}. "
                        f"Available window is only {int(duration_min)} min (< 30 min threshold)."
                    ),
                    why=_make_why(world, ev, commitment, walk_to_event, walk_to_class, rain_note),
                    actions=[],
                ))
                continue

            # Valid window — compute leave-by (unrounded, for reminder)
            leave_by = window_end_raw

            leave_str = leave_by.astimezone(_CAMPUS_TZ).strftime("%-I:%M %p")
            arrive_str = window_start.astimezone(_CAMPUS_TZ).strftime("%-I:%M %p")
            window_end_str = window_end.astimezone(_CAMPUS_TZ).strftime("%-I:%M %p")

            results.append(MoveSpec(
                key=key,
                kind="conflict",
                audience="student",
                policy="ask",
                urgency="today",
                impact="medium",
                title=f"Attend {ev_title} ({arrive_str}–{window_end_str})",
                summary=(
                    f"{ev_title} moved to today. Attend {arrive_str}–{window_end_str} "
                    f"before {commitment.title} at {commitment.start.strftime('%-I:%M %p')}. "
                    f"Must leave by {leave_str}.{rain_note}"
                ),
                why=_make_why(world, ev, commitment, walk_to_event, walk_to_class, rain_note),
                actions=[
                    {
                        "id": "visit-block",
                        "type": "create_calendar_block",
                        "params": {
                            "title": f"Attend: {ev_title}",
                            "start": window_start.isoformat(),
                            "end": window_end.isoformat(),
                            "location": ev_room_id,
                        },
                        "external": False,
                        "simulated": False,
                    },
                    {
                        "id": "leave-by-reminder",
                        "type": "add_reminder",
                        "params": {
                            "at": leave_by.isoformat(),
                            "message": (
                                f"Leave {ev_title} now — "
                                f"{commitment.title} starts at {commitment.start.strftime('%-I:%M %p')} "
                                f"({walk_to_class} min walk)."
                            ),
                        },
                        "external": False,
                        "simulated": False,
                    },
                ],
            ))

    return results


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _find_overlapping_commitments(world: World, ev_start: datetime, ev_end: datetime) -> list:
    """Return commitments that overlap the event window."""
    results = []
    ev_s = ev_start.astimezone(_CAMPUS_TZ)
    ev_e = ev_end.astimezone(_CAMPUS_TZ)
    for c in world.commitments:
        c_start = _loc_t(world.anchor_date, c.start)
        c_end = _loc_t(world.anchor_date, c.end)
        if c_start < ev_e and c_end > ev_s:
            results.append(c)
    return results


def _prev_commitment(world: World, ref_dt: datetime):
    """Commitment that ends latest before ref_dt."""
    ref_t = ref_dt.astimezone(_CAMPUS_TZ)
    prior = None
    for c in world.commitments:
        c_end = _loc_t(world.anchor_date, c.end)
        if c_end <= ref_t:
            if prior is None or c.end > prior.end:
                prior = c
    return prior


def _make_why(world: World, ev, commitment, walk_to_event: int, walk_to_class: int, rain_note: str) -> list[dict]:
    return [
        {
            "feed": "campus_events",
            "signal_id": None,
            "text": (
                f"{ev.title} overlaps {commitment.title}. "
                f"Walk to event: {walk_to_event} min; walk to class: {walk_to_class} min."
                + (f" {rain_note}" if rain_note else "")
            ),
        }
    ]


def _rain_windows(world: World) -> list[tuple[datetime, datetime]]:
    """Extract rain time windows from applied weather signals."""
    windows = []
    for sig in world.applied_signals:
        if sig.feed != "weather" or sig.kind != "forecast_change":
            continue
        try:
            payload = json.loads(sig.payload) if isinstance(sig.payload, str) else sig.payload
        except Exception:
            continue
        if payload.get("condition") != "rain":
            continue
        try:
            h0, m0 = map(int, payload["from"].split(":"))
            h1, m1 = map(int, payload["to"].split(":"))
            rs = _loc(world.anchor_date, h0, m0)
            re = _loc(world.anchor_date, h1, m1)
            windows.append((rs, re))
        except Exception:
            pass
    return windows


def _overlaps(s1: datetime, e1: datetime, s2: datetime, e2: datetime) -> bool:
    return s1 < e2 and e1 > s2


def _resolve_room_id(location_text: str, rooms: dict) -> str:
    if location_text in rooms:
        return location_text
    for rid, rdata in rooms.items():
        if rdata.get("name", "") == location_text:
            return rid
    return location_text


def _building_from_room(room_id: str, rooms: dict) -> str:
    if room_id in rooms:
        bld = rooms[room_id].get("building", "")
        if bld:
            return bld
    if "-" in room_id:
        return room_id.split("-")[0]
    return room_id

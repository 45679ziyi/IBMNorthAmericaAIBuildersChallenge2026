"""
Detector: disruption

Trigger 1: forecast_change signal with condition="rain"
  - Find outdoor walks in the rain window.
  - Emit umbrella reminder at end of class before the walk.

Trigger 2: incident signal (building_ops)
  - Student: informational move (policy=info)
  - Staff move is handled by ops_impact detector.
"""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta

import pytz

from app.services.campus.detectors.base import MoveSpec
from app.services.campus.world import World

_CAMPUS_TZ = pytz.timezone("America/New_York")


def _loc(anchor, h: int, m: int) -> datetime:
    """Localize campus wall time to timezone-aware datetime (pytz-safe)."""
    return _CAMPUS_TZ.localize(datetime(anchor.year, anchor.month, anchor.day, h, m))


def detect(world: World, now: datetime) -> list[MoveSpec]:
    results: list[MoveSpec] = []

    if now.tzinfo is None:
        now = now.replace(tzinfo=pytz.utc)

    results.extend(_detect_weather(world, now))
    results.extend(_detect_incident(world, now))
    return results


def _detect_weather(world: World, now: datetime) -> list[MoveSpec]:
    """Umbrella reminder for outdoor walks during a rain window."""
    results: list[MoveSpec] = []

    for sig in world.applied_signals:
        if sig.feed != "weather" or sig.kind != "forecast_change":
            continue

        try:
            payload = json.loads(sig.payload) if isinstance(sig.payload, str) else sig.payload
        except (json.JSONDecodeError, TypeError):
            payload = {}

        if payload.get("condition") != "rain":
            continue

        rain_from_str = payload.get("from", "")
        rain_to_str = payload.get("to", "")
        if not rain_from_str:
            continue

        h0, m0 = map(int, rain_from_str.split(":"))
        h1, m1 = map(int, rain_to_str.split(":"))
        rain_start = _loc(world.anchor_date, h0, m0)
        rain_end = _loc(world.anchor_date, h1, m1)

        # Find outdoor walks in the rain window
        # Outdoor = walk between buildings where route is NOT in covered_routes
        affected: list[dict] = []
        commitments = world.commitments
        for i in range(len(commitments)):
            c = commitments[i]
            class_start = _loc(world.anchor_date, c.start.hour, c.start.minute)
            if class_start < rain_start or class_start >= rain_end:
                continue

            # Determine prior building
            prior_bld = _prior_building(world, c)
            if prior_bld is None:
                prior_bld = world.scenario.get("persona", {}).get("start_place", "MEL")

            if prior_bld == c.building_id:
                continue  # same building, no walk

            if world.is_covered_route(prior_bld, c.building_id):
                continue  # covered route

            # Outdoor walk in rain window
            # Reminder at end of class before this one
            reminder_time = _class_end_before(world, c)
            if reminder_time is None:
                # No prior class: use class_start − walk − buffer
                walk_m = world.walk_minutes(prior_bld, c.building_id)
                reminder_time = class_start - timedelta(minutes=walk_m + world.walking_buffer)

            affected.append({
                "commitment": c,
                "from_building": prior_bld,
                "to_building": c.building_id,
                "walk_minutes": world.walk_minutes(prior_bld, c.building_id),
                "reminder_at": reminder_time,
                "class_start": class_start,
            })

        if not affected:
            continue

        # Use first affected walk's reminder time
        first = affected[0]
        reminder_at = first["reminder_at"]
        key_time = rain_from_str.replace(":", "")  # "1400"
        key = f"disruption:weather:rain-{key_time}"

        reminder_local = reminder_at.astimezone(_CAMPUS_TZ)
        reminder_str = reminder_local.strftime("%-I:%M %p")
        walk_str = f"{first['from_building']} → {first['to_building']}"
        commitment = first["commitment"]

        results.append(MoveSpec(
            key=key,
            kind="disruption",
            audience="student",
            policy="auto",
            urgency="today",
            impact="low",
            title=f"Umbrella reminder — rain {rain_from_str}–{rain_to_str}",
            summary=(
                f"Rain expected {rain_from_str}–{rain_to_str}. "
                f"Your walk {walk_str} ({first['walk_minutes']} min) is outdoors. "
                f"Reminder set for {reminder_str}."
            ),
            why=[{
                "feed": sig.feed,
                "signal_id": sig.id,
                "text": (
                    f"Rain {rain_from_str}–{rain_to_str} (p={payload.get('probability', '?')}). "
                    f"Walk {walk_str} is not covered."
                ),
            }],
            actions=[{
                "id": "umbrella-reminder",
                "type": "add_reminder",
                "params": {
                    "at": reminder_at.isoformat(),
                    "message": f"Take an umbrella — walk to {commitment.title} is outdoors.",
                },
                "external": False,
                "simulated": False,
            }],
        ))

    return results


def _detect_incident(world: World, now: datetime) -> list[MoveSpec]:
    """Informational student move for building_ops incidents."""
    results: list[MoveSpec] = []

    seen_incidents: set[str] = set()
    for sig in world.applied_signals:
        if sig.feed != "building_ops" or sig.kind != "incident":
            continue

        try:
            payload = json.loads(sig.payload) if isinstance(sig.payload, str) else sig.payload
        except (json.JSONDecodeError, TypeError):
            payload = {}

        incident_id = payload.get("incident_id", sig.id)
        if incident_id in seen_incidents:
            continue
        seen_incidents.add(incident_id)

        room_id = payload.get("room", "unknown")
        temp = payload.get("temperature_c")
        temp_str = f" ({temp}°C)" if temp is not None else ""

        # Find classes affected in this room (student info)
        affected = [c for c in world.commitments if c.room_id == room_id]
        if not affected:
            # No student impact
            continue

        affected_titles = ", ".join(c.title for c in affected)

        results.append(MoveSpec(
            key=f"disruption:{incident_id}:student",
            kind="disruption",
            audience="student",
            policy="info",
            urgency="today",
            impact="low",
            title=f"Building alert: {room_id}{temp_str}",
            summary=(
                f"{room_id} has an incident ({payload.get('type', 'unknown')}){temp_str}. "
                f"Affected: {affected_titles}. Facilities alerted (simulated)."
            ),
            why=[{
                "feed": sig.feed,
                "signal_id": sig.id,
                "text": sig.summary,
            }],
            actions=[],  # Info-only in M2
        ))

    return results


def _prior_building(world: World, commitment) -> str | None:
    """Building of the preceding commitment (the one ending just before this one)."""
    prior = None
    for c in world.commitments:
        if c.end <= commitment.start and c.id != commitment.id:
            if prior is None or c.start > prior.start:
                prior = c
    return prior.building_id if prior else None


def _class_end_before(world: World, commitment) -> datetime | None:
    """Return the end datetime of the class immediately before this commitment."""
    prior = None
    for c in world.commitments:
        if c.end <= commitment.start and c.id != commitment.id:
            if prior is None or c.end > prior.end:
                prior = c
    if prior is None:
        return None
    return _loc(world.anchor_date, prior.end.hour, prior.end.minute)

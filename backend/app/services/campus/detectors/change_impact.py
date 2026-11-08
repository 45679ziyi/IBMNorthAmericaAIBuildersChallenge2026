"""
Detector: change_impact

Trigger: a room_change signal applied since last evaluate.
Computes leave-by time = class start − walk(current_place, new_room) − buffer.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytz

from app.services.campus.detectors.base import MoveSpec
from app.services.campus.world import World

_CAMPUS_TZ = pytz.timezone("America/New_York")


def _loc(anchor: "date", t: "time") -> datetime:
    """Localize a wall-clock time on anchor date to campus timezone (pytz-safe)."""
    from datetime import date as _date, time as _time
    return _CAMPUS_TZ.localize(datetime(anchor.year, anchor.month, anchor.day, t.hour, t.minute))


def detect(world: World, now: datetime) -> list[MoveSpec]:
    """
    For each room_change signal in applied_signals:
    - Find the affected commitment in world.commitments
    - Compute leave-by = class_start − walk(prior_place, new_building) − buffer
    - Emit policy=auto move with update_event_location + add_reminder actions
    """
    results: list[MoveSpec] = []

    if now.tzinfo is None:
        now = now.replace(tzinfo=pytz.utc)

    persona = world.scenario.get("persona", {})
    start_place = persona.get("start_place", "MEL")

    for sig in world.applied_signals:
        if sig.kind != "room_change":
            continue

        try:
            payload = json.loads(sig.payload) if isinstance(sig.payload, str) else sig.payload
        except (json.JSONDecodeError, TypeError):
            payload = {}

        commitment_id = payload.get("commitment", "")
        new_room_id = payload.get("to", "")
        old_room_id = payload.get("from", "")

        # Find the commitment in the world
        commitment = next((c for c in world.commitments if c.id == commitment_id), None)
        if commitment is None:
            continue

        # Determine "current place" at the time of this class
        # = building where person would be after the preceding commitment
        prior_building = _prior_building(world, commitment, start_place)
        new_building = commitment.building_id  # already updated via apply_signal

        walk = world.walk_minutes(prior_building, new_building)
        # Convert class start to timezone-aware datetime
        class_start = _loc(world.anchor_date, commitment.start)
        leave_by = class_start - timedelta(minutes=walk + world.walking_buffer)

        # Check if any existing aurora_block would clash (informational in M2)
        clash_note = _check_block_clash(world, leave_by, commitment)

        # Signal time
        sig_at = sig.at_utc
        if sig_at is not None and sig_at.tzinfo is None:
            sig_at = sig_at.replace(tzinfo=pytz.utc)

        key = f"change:{commitment_id}:{sig.id}"

        # Human-readable times
        leave_by_local = leave_by.astimezone(_CAMPUS_TZ)
        leave_str = leave_by_local.strftime("%-I:%M %p")
        class_str = class_start.strftime("%-I:%M %p")

        summary = (
            f"{commitment.title} moved to {commitment.room_id}. "
            f"Leave by {leave_str} ({walk} min walk + {world.walking_buffer} min buffer)."
        )
        if clash_note:
            summary += f" Note: {clash_note}"

        why = [
            {
                "feed": sig.feed,
                "signal_id": sig.id,
                "text": (
                    f"{commitment.title} moved from {old_room_id} to {new_room_id}. "
                    f"Walk from {prior_building}: {walk} min."
                ),
            }
        ]

        actions = [
            {
                "id": "update-location",
                "type": "update_event_location",
                "params": {
                    "commitment_id": commitment_id,
                    "new_room": new_room_id,
                },
                "external": False,
                "simulated": False,
            },
            {
                "id": "leave-by-reminder",
                "type": "add_reminder",
                "params": {
                    "at": leave_by.isoformat(),
                    "message": f"Leave now for {commitment.title} ({commitment.room_id}). Walk: {walk} min.",
                },
                "external": False,
                "simulated": False,
            },
        ]

        results.append(MoveSpec(
            key=key,
            kind="change_impact",
            audience="student",
            policy="auto",
            urgency="today",
            impact="medium",
            title=f"Room change: {commitment.title}",
            summary=summary,
            why=why,
            actions=actions,
        ))

    return results


def _prior_building(world: World, commitment: object, start_place: str) -> str:
    """Return the building Alex would be in just before this commitment."""
    prior = None
    for c in world.commitments:
        if c.end <= commitment.start and c.id != commitment.id:
            if prior is None or c.start > prior.start:
                prior = c
    if prior is not None:
        return prior.building_id
    return start_place


def _check_block_clash(world: World, leave_by: datetime, commitment) -> str:
    """Check if any aurora_block ends after leave_by (for the period before the commitment)."""
    commitment_start = _loc(world.anchor_date, commitment.start)
    for c in world.commitments:
        if c.kind != "aurora_block":
            continue
        block_end = _loc(world.anchor_date, c.end)
        block_start = _loc(world.anchor_date, c.start)
        # Block overlaps the window [leave_by, commitment_start]
        if block_end > leave_by and block_start < commitment_start:
            return f"Existing block ends at {c.end.strftime('%H:%M')}, after leave-by {leave_by.strftime('%H:%M')}."
    return ""

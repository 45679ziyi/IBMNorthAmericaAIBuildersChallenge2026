"""
Detector: ops_impact

Trigger: incident signal (building_ops) — audience staff.
Identifies affected classes and feasible alternative rooms.
"""
from __future__ import annotations

import json
from datetime import datetime

import pytz

from app.services.campus.detectors.base import MoveSpec
from app.services.campus.world import World

_CAMPUS_TZ = pytz.timezone("America/New_York")


def _loc_t(anchor, t) -> datetime:
    return _CAMPUS_TZ.localize(datetime(anchor.year, anchor.month, anchor.day, t.hour, t.minute))


def detect(world: World, now: datetime) -> list[MoveSpec]:
    """
    For each incident signal:
    - Find all classes in the affected room.
    - Currently in-session → no relocation (facilities dispatch simulated).
    - Not yet started → find feasible alternative rooms (classroom, capacity ≥ enrolled, available).
    """
    results: list[MoveSpec] = []

    if now.tzinfo is None:
        now = now.replace(tzinfo=pytz.utc)

    now_local = now.astimezone(_CAMPUS_TZ)

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

        room_id = payload.get("room", "")
        if not room_id:
            continue

        # Find all classes today in the affected room
        affected_classes = [
            c for c in world.commitments
            if c.room_id == room_id and c.kind == "class"
        ]
        if not affected_classes:
            continue

        in_session: list = []
        not_started: list = []
        for c in affected_classes:
            c_start = _loc_t(world.anchor_date, c.start)
            c_end = _loc_t(world.anchor_date, c.end)
            if c_start <= now_local < c_end:
                in_session.append(c)
            elif c_start > now_local:
                not_started.append(c)

        total_students = sum(c.enrolled for c in affected_classes)
        num_classes = len(affected_classes)

        # Build actions for not-started classes
        actions: list[dict] = []
        for c in not_started:
            feasible = _feasible_rooms(world, c, room_id)
            for room in feasible:
                actions.append({
                    "id": f"request-room-{c.id}-{room['id']}",
                    "type": "request_room_change",
                    "params": {
                        "commitment_id": c.id,
                        "current_room": room_id,
                        "proposed_room": room["id"],
                        "proposed_room_name": room.get("name", room["id"]),
                        "capacity": room.get("capacity", 0),
                        "enrolled": c.enrolled,
                    },
                    "external": False,
                    "simulated": True,
                })

        # Summary
        in_session_names = ", ".join(c.title for c in in_session) if in_session else "none"
        not_started_names = ", ".join(c.title for c in not_started) if not_started else "none"

        room_info = world.rooms.get(room_id, {})
        temp = payload.get("temperature_c")
        temp_str = f" ({temp}°C)" if temp is not None else ""

        summary_parts = [
            f"Incident in {room_id}{temp_str} ({payload.get('type', 'unknown')}).",
            f"Affected: {num_classes} class(es), {total_students} students.",
        ]
        if in_session:
            summary_parts.append(f"Currently in-session: {in_session_names} — facilities alerted (simulated).")
        if not_started:
            feasible_rooms = list({
                a["params"]["proposed_room"] for a in actions
            })
            summary_parts.append(
                f"Not yet started: {not_started_names}. "
                f"Feasible alternative(s): {', '.join(feasible_rooms) if feasible_rooms else 'none found'}."
            )

        results.append(MoveSpec(
            key=f"ops:{incident_id}",
            kind="ops_impact",
            audience="staff",
            policy="ask",
            urgency="high",
            impact="high",
            title=f"Ops alert: {room_id} incident — {num_classes} class(es), {total_students} students",
            summary=" ".join(summary_parts),
            why=[{
                "feed": sig.feed,
                "signal_id": sig.id,
                "text": sig.summary,
            }],
            actions=actions,
        ))

    return results


def _feasible_rooms(world: World, commitment, excluded_room: str) -> list[dict]:
    """
    Find feasible alternative rooms:
    - kind == "classroom"
    - capacity >= commitment.enrolled
    - available == True
    - not the incident room
    - no conflicting class at the same time
    """
    results: list[dict] = []
    c_start = commitment.start
    c_end = commitment.end

    for room_id, room in world.rooms.items():
        if room_id == excluded_room:
            continue
        if room.get("kind") != "classroom":
            continue
        if not room.get("available", False):
            continue
        if room.get("capacity", 0) < commitment.enrolled:
            continue
        # Check no conflicting class at the same time
        conflict = any(
            other.room_id == room_id and other.id != commitment.id
            and _times_overlap(other.start, other.end, c_start, c_end)
            for other in world.commitments
        )
        if conflict:
            continue
        results.append({"id": room_id, **room})

    return results


def _times_overlap(s1, e1, s2, e2) -> bool:
    return s1 < e2 and e1 > s2

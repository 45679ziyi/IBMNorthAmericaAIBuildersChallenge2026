"""
Detector: group_opportunity

Trigger: open group task due within 72 h with group.meeting_minutes specified.
Finds earliest slot that works for all teammates and a bookable room.
"""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta

import pytz

from app.services.campus.detectors.base import MoveSpec
from app.services.campus.world import World, _round_up_5

_CAMPUS_TZ = pytz.timezone("America/New_York")
_HORIZON_HOURS = 80   # generous horizon: task due within ~3 days + some slack
_APPEAR_BEFORE_MINUTES = 90  # emit move up to 90 min before the slot


def _loc(anchor, h: int, m: int) -> datetime:
    return _CAMPUS_TZ.localize(datetime(anchor.year, anchor.month, anchor.day, h, m))


def detect(world: World, now: datetime) -> list[MoveSpec]:
    """
    For each group task due within 72 h with meeting_minutes:
    - Intersect student's free windows with each teammate's free time.
    - Find earliest slot in a bookable room of sufficient size.
    - Emit policy=ask move if slot found.
    """
    results: list[MoveSpec] = []

    if now.tzinfo is None:
        now = now.replace(tzinfo=pytz.utc)

    now_local = now.astimezone(_CAMPUS_TZ)
    deadline_cutoff = now + timedelta(hours=_HORIZON_HOURS)

    # Get group task info from scenario fixture (tasks list has group field)
    scenario_tasks_by_id: dict[str, dict] = {
        t["id"]: t for t in world.scenario.get("tasks", [])
    }

    for task in world.tasks:
        due = task.due_at_utc
        if due is None:
            continue
        if due.tzinfo is None:
            due = due.replace(tzinfo=pytz.utc)
        if due > deadline_cutoff:
            continue
        if task.status == "done":
            continue

        # Find the scenario task definition to get group info
        # Match by course_label or title
        scenario_def = _find_scenario_task(world.scenario, task)
        if scenario_def is None:
            continue
        group = scenario_def.get("group")
        if not group:
            continue
        meeting_minutes = group.get("meeting_minutes", 0)
        if meeting_minutes <= 0:
            continue

        # Student's free windows from now
        student_windows = world.free_windows(now)

        if not student_windows:
            continue

        # Compute teammate availability (complement of busy within campus hours)
        teammate_free: list[list[tuple[datetime, datetime]]] = []
        for tm in world.teammates:
            tm_free = _teammate_free_windows(tm, world.anchor_date)
            teammate_free.append(tm_free)

        # Intersect all free windows
        combined = student_windows
        for tf in teammate_free:
            combined = _intersect_windows(combined, tf)

        if not combined:
            continue

        # Find earliest slot of at least meeting_minutes
        slot = _find_slot(combined, meeting_minutes)
        if slot is None:
            continue

        slot_start, slot_end = slot

        # Only appear up to 90 min before slot start
        if now_local > slot_start:
            continue
        if (slot_start - now_local).total_seconds() > _APPEAR_BEFORE_MINUTES * 60:
            # Not yet time to suggest this
            continue

        # Find a bookable room with enough capacity
        group_size = len(world.teammates) + 1  # +1 for student
        room = _find_room(world, slot_start.time(), slot_end.time(), group_size)
        if room is None:
            continue

        room_id = room["id"]
        room_name = room.get("name", room_id)

        # Slot: start to start + meeting_minutes
        actual_end = slot_start + timedelta(minutes=meeting_minutes)
        start_str = slot_start.strftime("%-I:%M %p")
        end_str = actual_end.strftime("%-I:%M %p")
        teammate_names = ", ".join(tm["name"] for tm in world.teammates)

        results.append(MoveSpec(
            key=f"group:{task.id}:slot",
            kind="group_opportunity",
            audience="student",
            policy="ask",
            urgency="today",
            impact="medium",
            title=f"Group meeting: {task.title}",
            summary=(
                f"Everyone free {start_str}–{end_str} in {room_name}. "
                f"Team: {teammate_names}."
            ),
            why=[{
                "feed": "library_rooms",
                "signal_id": None,
                "text": (
                    f"Group task '{task.title}' due in < 72 h. "
                    f"Team has a common window {start_str}–{end_str}; {room_name} is available."
                ),
            }],
            actions=[
                {
                    "id": "book-room",
                    "type": "book_room",
                    "params": {
                        "room_id": room_id,
                        "start": slot_start.isoformat(),
                        "end": actual_end.isoformat(),
                    },
                    "external": False,
                    "simulated": True,
                },
                {
                    "id": "draft-invite",
                    "type": "draft_message",
                    "params": {
                        "to": [tm["id"] for tm in world.teammates],
                        "subject": f"Group meeting: {task.title}",
                        "body": (
                            f"Hi team, let's meet {start_str}–{end_str} in {room_name} "
                            f"for the {task.title}."
                        ),
                        "draft_only": True,  # NEVER sent automatically
                    },
                    "external": False,
                    "simulated": True,
                },
                {
                    "id": "calendar-block",
                    "type": "create_calendar_block",
                    "params": {
                        "title": f"Group meeting: {task.title}",
                        "start": slot_start.isoformat(),
                        "end": actual_end.isoformat(),
                        "location": room_id,
                    },
                    "external": False,
                    "simulated": False,
                },
            ],
        ))

    return results


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _find_scenario_task(scenario: dict, task) -> dict | None:
    """Match an ORM Task to its scenario fixture definition."""
    for st in scenario.get("tasks", []):
        # Match by course_label or title substring
        if task.course_label and st.get("course") == task.course_label:
            if "group" in st:
                return st
        if st.get("title", "").lower() in task.title.lower():
            return st
    return None


def _teammate_free_windows(
    teammate: dict,
    anchor: "date",
) -> list[tuple[datetime, datetime]]:
    """Return free windows for a teammate (complement of busy within campus hours)."""
    campus_open = _loc(anchor, 8, 0)
    campus_close = _loc(anchor, 20, 0)

    busy: list[tuple[datetime, datetime]] = []
    for slot in teammate.get("busy", []):
        h0, m0 = map(int, slot[0].split(":"))
        h1, m1 = map(int, slot[1].split(":"))
        s = _loc(anchor, h0, m0)
        e = _loc(anchor, h1, m1)
        busy.append((s, e))

    busy.sort(key=lambda x: x[0])

    free: list[tuple[datetime, datetime]] = []
    cursor = campus_open
    for bs, be in busy:
        if bs > cursor:
            free.append((cursor, bs))
        cursor = max(cursor, be)
    if cursor < campus_close:
        free.append((cursor, campus_close))

    return free


def _intersect_windows(
    a: list[tuple[datetime, datetime]],
    b: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """Intersect two sorted lists of non-overlapping time windows."""
    result: list[tuple[datetime, datetime]] = []
    i = j = 0
    while i < len(a) and j < len(b):
        start = max(a[i][0], b[j][0])
        end = min(a[i][1], b[j][1])
        if end > start:
            result.append((start, end))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return result


def _find_slot(
    windows: list[tuple[datetime, datetime]],
    minutes: int,
) -> tuple[datetime, datetime] | None:
    """Find the earliest window of at least `minutes` length; round start up to 5 min."""
    for w_start, w_end in windows:
        candidate_start = _round_up_5(w_start)
        candidate_end = candidate_start + timedelta(minutes=minutes)
        if candidate_end <= w_end:
            return (candidate_start, candidate_end)
    return None


def _find_room(
    world: World,
    slot_start: time,
    slot_end: time,
    min_capacity: int,
) -> dict | None:
    """Find a bookable room available for the slot with capacity ≥ min_capacity."""
    for room_id, avail_slots in world.room_availability.items():
        room = world.rooms.get(room_id)
        if room is None:
            continue
        if room.get("capacity", 0) < min_capacity:
            continue
        if not room.get("bookable", False):
            continue
        # Check if any availability slot covers [slot_start, slot_end]
        for avail_start, avail_end in avail_slots:
            if avail_start <= slot_start and avail_end >= slot_end:
                return {"id": room_id, **room}
    return None

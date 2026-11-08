"""Deterministic daily planning engine.

Algorithm (v1):
  1. Resolve the target date in the user's timezone.
  2. Collect fixed calendar events for that day.
  3. Sort open tasks by deadline, priority, then creation time.
  4. Compute free intervals between fixed events within user availability.
  5. For each task, fit it into the earliest available interval.
  6. Insert break blocks between focus blocks per user preferences.
  7. Return draft DailyPlan with blocks, unscheduled list, and warnings.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone, date
from typing import Any

import pytz
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.models.models import (
    CalendarEvent,
    Task,
    DailyPlan,
    PlanBlock,
    UserPreference,
)
from app.schemas.schemas import DailyPlanRead, PlanBlockRead
from app.core.config import settings

PRIORITY_ORDER = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
ALGO_VERSION = "v1"


def _ensure_utc(dt: datetime) -> datetime:
    """Return a UTC-aware datetime; assume UTC if naive."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def generate_plan(db: Session, user_id: str, plan_date: str, tz_name: str) -> DailyPlanRead:
    """Generate a deterministic draft daily plan."""
    # Load user preferences (or defaults)
    pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    day_start_str = pref.day_start_time if pref else "08:00"
    day_end_str = pref.day_end_time if pref else "22:00"
    focus_mins = pref.preferred_focus_block_minutes if pref else 50
    short_break = pref.short_break_minutes if pref else 10

    tz = pytz.timezone(tz_name)
    target_date = date.fromisoformat(plan_date)

    # Build availability window in UTC
    def _local_dt(time_str: str) -> datetime:
        h, m = map(int, time_str.split(":"))
        local = tz.localize(datetime(target_date.year, target_date.month, target_date.day, h, m))
        return local.astimezone(timezone.utc)

    avail_start = _local_dt(day_start_str)
    avail_end = _local_dt(day_end_str)

    # Collect fixed events for the day
    fixed_events = _get_day_events(db, user_id, avail_start, avail_end)
    fixed_events.sort(key=lambda e: e.start_at_utc)

    # Detect overlapping fixed events
    warnings: list[str] = []
    for i in range(len(fixed_events) - 1):
        a, b = fixed_events[i], fixed_events[i + 1]
        if b.start_at_utc < a.end_at_utc:
            warnings.append(
                f"Overlap detected: '{a.title}' and '{b.title}' overlap between "
                f"{b.start_at_utc.isoformat()} and {a.end_at_utc.isoformat()}."
            )

    # Collect open, non-done tasks
    now_utc = get_now()
    tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user_id,
            Task.status.in_(["todo", "in_progress"]),
        )
        .all()
    )

    # Flag overdue tasks (ensure UTC-aware comparison)
    for t in tasks:
        due = _ensure_utc(t.due_at_utc) if t.due_at_utc else None
        if due and due < now_utc:
            warnings.append(f"Task '{t.title}' is overdue (due {due.isoformat()}).")

    # Sort: overdue first, then by due date, then priority, then creation time
    def _sort_key(t: Task):
        due = _ensure_utc(t.due_at_utc) if t.due_at_utc else None
        overdue = 0 if (due and due < now_utc) else 1
        sort_due = due or datetime(9999, 12, 31, tzinfo=timezone.utc)
        pri = PRIORITY_ORDER.get(t.priority, 2)
        created = _ensure_utc(t.created_at) if t.created_at else now_utc
        return (overdue, sort_due, pri, created)

    tasks.sort(key=_sort_key)

    # Build free intervals from fixed events
    free_intervals = _compute_free_intervals(avail_start, avail_end, fixed_events)

    # Create plan blocks for fixed events
    plan_blocks: list[dict[str, Any]] = []
    for ev in fixed_events:
        plan_blocks.append({
            "task_id": None,
            "calendar_event_id": ev.id,
            "title": ev.title,
            "start_at_utc": ev.start_at_utc,
            "end_at_utc": ev.end_at_utc,
            "block_type": "fixed_event",
            "reason": f"Imported fixed event: '{ev.title}'.",
            "is_user_edited": False,
        })

    # Schedule tasks into free intervals
    unscheduled: list[dict[str, Any]] = []
    focus_block_count = 0

    for task in tasks:
        # Skip tasks whose deadline is before avail_start (UTC-aware)
        task_due_check = _ensure_utc(task.due_at_utc) if task.due_at_utc else None
        if task_due_check and task_due_check < avail_start:
            unscheduled.append({
                "task_id": task.id,
                "title": task.title,
                "reason": f"Overdue (deadline {task_due_check.isoformat()} already passed).",
            })
            continue

        # Determine how long the task needs
        needed = timedelta(minutes=task.estimated_minutes)

        # Insert a break before this task block if needed
        scheduled = False
        for interval in free_intervals:
            slot_start, slot_end = interval

            # Insert short break if this is not the first focus block
            actual_start = slot_start
            if focus_block_count > 0:
                break_end = slot_start + timedelta(minutes=short_break)
                if break_end + needed <= slot_end:
                    plan_blocks.append({
                        "task_id": None,
                        "calendar_event_id": None,
                        "title": "Break",
                        "start_at_utc": slot_start,
                        "end_at_utc": break_end,
                        "block_type": "break",
                        "reason": f"Short break ({short_break} min) between focus blocks.",
                        "is_user_edited": False,
                    })
                    actual_start = break_end
                # else: skip the break if there isn't room — still try to fit the task

            task_end = actual_start + needed

            # Check deadline constraint (UTC-aware)
            task_due = _ensure_utc(task.due_at_utc) if task.due_at_utc else None
            if task_due and task_end > task_due:
                continue

            if task_end <= slot_end:
                plan_blocks.append({
                    "task_id": task.id,
                    "calendar_event_id": None,
                    "title": task.title,
                    "start_at_utc": actual_start,
                    "end_at_utc": task_end,
                    "block_type": "task",
                    "reason": (
                        f"Scheduled in first available {task.estimated_minutes}-minute window. "
                        f"Priority: {task.priority}."
                        + (f" Due: {task.due_at_utc.strftime('%Y-%m-%d %H:%M UTC')}." if task.due_at_utc else "")
                    ),
                    "is_user_edited": False,
                })
                # Consume time from this free interval
                interval[0] = task_end
                focus_block_count += 1
                scheduled = True
                break

        if not scheduled:
            unscheduled.append({
                "task_id": task.id,
                "title": task.title,
                "reason": (
                    "No available time window could fit this task today. "
                    "Consider reducing estimated duration or rescheduling."
                ),
            })

    # Validate: no overlapping plan blocks
    all_timed = [b for b in plan_blocks]
    all_timed.sort(key=lambda b: b["start_at_utc"])
    for i in range(len(all_timed) - 1):
        a, b = all_timed[i], all_timed[i + 1]
        if b["start_at_utc"] < a["end_at_utc"]:
            warnings.append(
                f"Planner overlap detected: '{a['title']}' and '{b['title']}'. This is a bug."
            )

    # Persist to DB
    plan = DailyPlan(
        user_id=user_id,
        plan_date=plan_date,
        timezone=tz_name,
        algorithm_version=ALGO_VERSION,
        status="draft",
    )
    db.add(plan)
    db.flush()

    for block_data in plan_blocks:
        pb = PlanBlock(daily_plan_id=plan.id, **block_data)
        db.add(pb)

    db.commit()
    db.refresh(plan)

    result = DailyPlanRead.model_validate(plan)
    result.unscheduled = unscheduled
    result.warnings = warnings
    return result


def _get_day_events(
    db: Session, user_id: str, start: datetime, end: datetime
) -> list[CalendarEvent]:
    """Return calendar events that overlap with [start, end)."""
    return (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.user_id == user_id,
            CalendarEvent.start_at_utc < end,
            CalendarEvent.end_at_utc > start,
        )
        .all()
    )


def _compute_free_intervals(
    avail_start: datetime, avail_end: datetime, fixed_events: list[CalendarEvent]
) -> list[list[datetime]]:
    """Return mutable list of [start, end] free intervals between fixed events."""
    fixed_events = sorted(fixed_events, key=lambda e: e.start_at_utc)
    intervals: list[list[datetime]] = []
    cursor = avail_start

    for ev in fixed_events:
        ev_start = max(_ensure_utc(ev.start_at_utc), avail_start)
        ev_end = min(_ensure_utc(ev.end_at_utc), avail_end)
        if ev_start > cursor:
            intervals.append([cursor, ev_start])
        cursor = max(cursor, ev_end)

    if cursor < avail_end:
        intervals.append([cursor, avail_end])

    # Filter out zero/negative-length intervals
    return [iv for iv in intervals if iv[1] > iv[0]]

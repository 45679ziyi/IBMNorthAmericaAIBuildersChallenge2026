"""
Detector: deadline_risk

Trigger: open task with estimated_minutes > 0 and due within 36 hours.
Schedules study blocks into free windows (earliest-first, max 90 min per block).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytz

from app.services.campus.detectors.base import MoveSpec
from app.services.campus.world import World, _round_up_5, _round_down_5

_CAMPUS_TZ = pytz.timezone("America/New_York")
_HORIZON_HOURS = 36
_MAX_BLOCK = 90      # max minutes per block
_MIN_BLOCK = 30      # min window to bother with


def detect(world: World, now: datetime) -> list[MoveSpec]:
    """
    For each open task due within 36 h with estimated_minutes > 0:
    - Check if existing aurora_blocks already cover the estimate.
    - Use free_windows to place study blocks (earliest-first, max 90 min).
    - If all minutes fit: policy=auto; else policy=ask with note.
    """
    results: list[MoveSpec] = []

    if now.tzinfo is None:
        now = now.replace(tzinfo=pytz.utc)

    deadline_cutoff = now + timedelta(hours=_HORIZON_HOURS)

    for task in world.tasks:
        if task.estimated_minutes <= 0:
            continue
        if task.status == "done":
            continue
        due = task.due_at_utc
        if due is None:
            continue
        # Normalise due to timezone-aware
        if due.tzinfo is None:
            due = due.replace(tzinfo=pytz.utc)
        if due > deadline_cutoff:
            continue

        # Check if aurora_blocks already cover this task
        covered = _covered_minutes(world, task)
        remaining = task.estimated_minutes - covered
        if remaining <= 0:
            continue

        # Compute free windows
        windows = world.free_windows(now)

        # Only keep windows that end before the deadline
        windows = [
            (s, e) for (s, e) in windows
            if s < due
        ]
        # Trim any window that extends past the deadline
        trimmed: list[tuple[datetime, datetime]] = []
        for s, e in windows:
            if e > due:
                e = due
            if (e - s).total_seconds() >= _MIN_BLOCK * 60:
                trimmed.append((s, e))
        windows = trimmed

        # Place blocks greedily
        blocks: list[dict] = []
        to_place = remaining
        for w_start, w_end in windows:
            if to_place <= 0:
                break
            avail = int((w_end - w_start).total_seconds() // 60)
            if avail < _MIN_BLOCK:
                continue
            # How much to place in this window
            place = min(to_place, _MAX_BLOCK, avail)
            # If the remainder is less than _MIN_BLOCK but this is the last needed chunk, still place it
            if place < _MIN_BLOCK:
                if to_place <= place:
                    # Final chunk, place anyway
                    pass
                else:
                    continue
            block_end = w_start + timedelta(minutes=place)
            blocks.append({
                "window_start": w_start.isoformat(),
                "window_end": block_end.isoformat(),
                "minutes": place,
            })
            to_place -= place

        all_fit = (to_place <= 0)

        if not blocks:
            # No windows at all — policy ask
            spec = _make_spec(
                task=task,
                blocks=[],
                all_fit=False,
                remaining=remaining,
                placed=0,
                due=due,
            )
            results.append(spec)
            continue

        results.append(_make_spec(
            task=task,
            blocks=blocks,
            all_fit=all_fit,
            remaining=remaining,
            placed=remaining - max(to_place, 0),
            due=due,
        ))

    return results


def _covered_minutes(world: World, task) -> int:
    """Return total aurora_block minutes already scheduled for this task."""
    # In M2 there are no aurora_blocks yet (M3 executes them), so always 0.
    # This function is a hook for M3.
    return 0


def _make_spec(task, blocks: list[dict], all_fit: bool,
               remaining: int, placed: int, due: datetime) -> MoveSpec:
    due_local = due.astimezone(_CAMPUS_TZ)
    due_str = due_local.strftime("%-I:%M %p")

    if all_fit:
        policy = "auto"
        urgency = "today"
        summary = (
            f"Study blocks scheduled for '{task.title}' (due {due_str}). "
            f"All {remaining} min placed."
        )
    else:
        policy = "ask"
        urgency = "high"
        summary = (
            f"Only {placed} of {remaining} min fit before the deadline ({due_str}). "
            f"Confirm or adjust."
        )

    actions = [
        {
            "id": f"block-{i}",
            "type": "create_calendar_block",
            "params": {
                "title": f"Study: {task.title}",
                "start": b["window_start"],
                "end": b["window_end"],
                "task_id": task.id,
            },
            "external": False,
            "simulated": False,
        }
        for i, b in enumerate(blocks)
    ]

    why_text = (
        f"Task '{task.title}' due {due_local.strftime('%a %-I:%M %p')}, "
        f"{task.estimated_minutes} min estimated"
    )

    return MoveSpec(
        key=f"deadline:{task.id}",
        kind="deadline_risk",
        audience="student",
        policy=policy,
        urgency=urgency,
        impact="high" if not all_fit else "medium",
        title=f"Study time for: {task.title}",
        summary=summary,
        why=[{"feed": "brightspace", "signal_id": task.source_signal_id, "text": why_text}],
        actions=actions,
    )

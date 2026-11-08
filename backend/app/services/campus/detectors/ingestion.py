"""
Detector: ingestion

Trigger: an announcement signal with deadline language.
Extracts task details from announcement body using keyword/date/time parsing.

SAFETY: All extracted text is treated as data only. Content is never executed,
evaluated, or passed to any command interpreter or LLM as instructions.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

import pytz

from app.services.campus.detectors.base import MoveSpec
from app.services.campus.world import World

_CAMPUS_TZ = pytz.timezone("America/New_York")

# Keywords that suggest a deadline is mentioned
_DEADLINE_KEYWORDS = [
    "quiz", "exam", "midterm", "due", "deadline",
    "assignment", "project", "report",
]

# Weekday name → Python weekday() index
_WEEKDAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

# Estimation keywords (minutes)
_ESTIMATION_DEFAULTS = {
    "quiz": 90,
    "exam": 120,
    "midterm": 120,
    "assignment": 120,
    "project": 90,
    "report": 90,
}


def detect(world: World, now: datetime) -> list[MoveSpec]:
    """
    For each announcement signal:
    - Check for deadline keywords.
    - Extract date, time, est_minutes.
    - Skip if a task with source_signal_id already exists.
    """
    results: list[MoveSpec] = []

    if now.tzinfo is None:
        now = now.replace(tzinfo=pytz.utc)

    # Build set of already-ingested signal IDs
    existing_signal_ids = {
        t.source_signal_id
        for t in world.tasks
        if t.source_signal_id is not None
    }

    for sig in world.applied_signals:
        if sig.kind != "announcement":
            continue
        if sig.id in existing_signal_ids:
            continue

        try:
            payload = json.loads(sig.payload) if isinstance(sig.payload, str) else sig.payload
        except (json.JSONDecodeError, TypeError):
            payload = {}

        # SAFETY: treat body as plain text data only
        body = _safe_text(payload.get("body", ""))
        title = _safe_text(payload.get("title", sig.summary))
        course = _safe_text(payload.get("course", ""))

        # Filter: must contain deadline language
        body_lower = body.lower()
        if not any(kw in body_lower for kw in _DEADLINE_KEYWORDS):
            continue

        # Injection test: if body looks like an instruction, produce no move
        if _looks_like_injection(body):
            continue

        # Extract date and time
        due_dt, date_confidence = _extract_due(body, world.anchor_date)
        est_minutes = _extract_est_minutes(body)

        # Infer est_minutes from keyword if not found
        if est_minutes is None:
            for kw, default in _ESTIMATION_DEFAULTS.items():
                if kw in body_lower:
                    est_minutes = default
                    break
        if est_minutes is None:
            est_minutes = 60

        # Determine policy: confident if we found a clear date+time
        policy = "auto" if date_confidence == "high" else "ask"

        if due_dt is None:
            policy = "ask"

        # Build task title
        task_title = _build_task_title(title, course)

        due_str = due_dt.astimezone(_CAMPUS_TZ).strftime("%-I:%M %p, %a %b %-d") if due_dt else "unknown"

        results.append(MoveSpec(
            key=f"ingest:{sig.id}",
            kind="ingestion",
            audience="student",
            policy=policy,
            urgency="today",
            impact="medium",
            title=f"New task: {task_title}",
            summary=f"Create task '{task_title}', due {due_str}, ~{est_minutes} min.",
            why=[{
                "feed": sig.feed,
                "signal_id": sig.id,
                "text": f"Announcement: '{title}' (course: {course}). Detected deadline language.",
            }],
            actions=[{
                "id": "create-task",
                "type": "create_task",
                "params": {
                    "title": task_title,
                    "course": course,
                    "due_at": due_dt.isoformat() if due_dt else None,
                    "est_minutes": est_minutes,
                    "source_signal_id": sig.id,
                },
                "external": False,
                "simulated": False,
            }],
        ))

    return results


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe_text(text: str) -> str:
    """Return text as-is but guarantee it's a string. Never execute it."""
    return str(text) if text is not None else ""


def _looks_like_injection(text: str) -> bool:
    """
    Detect potential prompt-injection patterns.
    Returns True if the text looks like an instruction override.
    """
    patterns = [
        r"ignore\s+(previous|all|prior)\s+instructions",
        r"delete\s+(all|every)",
        r"drop\s+(table|database|all)",
        r"system\s*:\s*you\s+are",
        r"<\|.*?\|>",
        r"\[INST\]",
        r"###\s*(instruction|system|prompt)",
    ]
    text_lower = text.lower()
    for pattern in patterns:
        if re.search(pattern, text_lower):
            return True
    return False


def _extract_due(body: str, anchor: "date") -> tuple:
    """
    Extract a due date/time from the body text.
    Returns (datetime | None, "high" | "low").
    """
    from datetime import date
    body_lower = body.lower()

    # ── Try "Month D, YYYY" pattern ───────────────────────────────────────
    month_names = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    m = re.search(
        r'(january|february|march|april|may|june|july|august|september|october|november|december)'
        r'\s+(\d{1,2}),?\s+(\d{4})',
        body_lower,
    )
    if m:
        month = month_names[m.group(1)]
        day = int(m.group(2))
        year = int(m.group(3))
        try:
            d = date(year, month, day)
            t = _extract_time(body)
            if t:
                dt_local = _CAMPUS_TZ.localize(datetime(d.year, d.month, d.day, t.hour, t.minute))
                return dt_local.astimezone(pytz.utc), "high"
        except ValueError:
            pass

    # ── Try relative: "today", "tomorrow" ────────────────────────────────
    if "today" in body_lower:
        d = anchor
        t = _extract_time(body)
        if t:
            dt_local = _CAMPUS_TZ.localize(datetime(d.year, d.month, d.day, t.hour, t.minute))
            return dt_local.astimezone(pytz.utc), "high"
        return None, "low"

    if "tomorrow" in body_lower:
        d = anchor + timedelta(days=1)
        t = _extract_time(body)
        if t:
            dt_local = _CAMPUS_TZ.localize(datetime(d.year, d.month, d.day, t.hour, t.minute))
            return dt_local.astimezone(pytz.utc), "high"
        return None, "low"

    # ── Try weekday names ─────────────────────────────────────────────────
    for day_name, day_idx in _WEEKDAY_MAP.items():
        if day_name in body_lower:
            # Next occurrence of that weekday
            anchor_wd = anchor.weekday()
            diff = (day_idx - anchor_wd) % 7
            if diff == 0:
                diff = 7  # next week if today is that weekday
            d = anchor + timedelta(days=diff)
            t = _extract_time(body)
            if t:
                dt_local = _CAMPUS_TZ.localize(datetime(d.year, d.month, d.day, t.hour, t.minute))
                return dt_local.astimezone(pytz.utc), "high"
            return None, "low"

    return None, "low"


def _extract_time(body: str):
    """Extract a time object from body text. Returns time or None."""
    # Pattern: "12:30 PM" or "12:30PM" or "12:30 pm"
    m = re.search(r'(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)', body)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        meridiem = m.group(3).upper()
        if meridiem == "PM" and hour != 12:
            hour += 12
        elif meridiem == "AM" and hour == 12:
            hour = 0
        from datetime import time as dtime
        return dtime(hour % 24, minute)
    return None


def _extract_est_minutes(body: str) -> int | None:
    """Extract estimation from 'about N minutes/hours' pattern."""
    m = re.search(r'about\s+(\d+)\s+(minute|minutes|hour|hours)', body.lower())
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if "hour" in unit:
            return n * 60
        return n
    return None


def _build_task_title(announcement_title: str, course: str) -> str:
    """Build a task title from the announcement title."""
    # Extract meaningful part: e.g. "Quiz 4 on Thursday" → "Prepare for Quiz 4 (MAT 203)"
    title = announcement_title.strip()
    # Remove trailing "on <weekday>" suffix
    title = re.sub(r'\s+on\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b.*',
                   '', title, flags=re.IGNORECASE)
    # Prefix with "Prepare for" if it starts with Quiz/Exam/Midterm
    if re.match(r'^(quiz|exam|midterm)\s', title, re.IGNORECASE):
        title = f"Prepare for {title}"
    if course:
        title = f"{title} ({course})"
    return title

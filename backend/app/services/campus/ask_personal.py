"""
Personal-context answerer — M5.

Rule-matched intents, no LLM required.
Each answer lists its sources with feed and time.
Same supported / partial / not_found labels as the public retriever.

In scenario mode: answers from the sim world (CalendarEvents, Signals).
In real mode: gracefully returns partial/not_found for personal intents.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pytz
from sqlalchemy.orm import Session

_CAMPUS_TZ = pytz.timezone("America/New_York")

# ─── PersonalAnswer ───────────────────────────────────────────────────────────

@dataclass
class PersonalAnswer:
    answer: str
    coverage: str  # "supported" | "partial" | "not_found"
    sources: list[dict] = field(default_factory=list)
    intent: str = ""


# ─── Intent keywords ──────────────────────────────────────────────────────────

INTENTS: dict[str, list[str]] = {
    "next_commitment": [
        r"\bnext class\b", r"\bnext commitment\b", r"\bwhere.*need.*be\b",
        r"\bwhere.*need.*go\b", r"\bwhere.*i.*go\b", r"\bwhere.*do.*i.*go\b",
        r"\bwhere.*i.*need\b", r"\bwhere.*be next\b", r"\bgo next\b",
        r"\bbe next\b",
    ],
    "what_changed": [
        r"\bwhat changed\b", r"\bchanged today\b", r"\bupdates today\b",
        r"\bwhat happened\b", r"\bwhat.*update\b", r"\bany.*change\b",
    ],
    "why_moved": [
        r"\bwhy.*moved\b", r"\bwhy.*change\b", r"\bmoved to\b",
        r"\brelocated\b", r"\bwhy.*room\b",
    ],
    "time_to_finish": [
        r"\bfinish\b", r"\benough time\b", r"\bcan i finish\b",
        r"\btime for\b", r"\bcomplete\b", r"\btime.*assignment\b",
        r"\bassignment.*tonight\b", r"\btonight\b",
    ],
    "room_status": [
        r"\bis.*okay\b", r"\bis.*ok\b", r"\bstatus of\b",
        r"\bwhat.*room\b", r"\btemperature\b", r"\bhvac\b",
        r"\broom.*status\b", r"\bbuilding.*status\b",
    ],
}


def match_intent(question: str) -> Optional[str]:
    """Return intent name or None."""
    q = question.lower()
    for intent, patterns in INTENTS.items():
        for pat in patterns:
            if re.search(pat, q):
                return intent
    return None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _fmt_time(dt: datetime) -> str:
    local = dt.astimezone(_CAMPUS_TZ)
    return local.strftime("%I:%M %p").lstrip("0")


def _get_sim_state(db: Session):
    from app.models.models import SimState
    return db.get(SimState, 1)


def _get_scenario(db: Session) -> Optional[dict]:
    state = _get_sim_state(db)
    if state is None or state.mode != "scenario" or not state.scenario_id:
        return None
    from app.services.campus.scenario import load_scenario
    try:
        return load_scenario(state.scenario_id)
    except FileNotFoundError:
        return None


def _get_applied_signal_ids(db: Session) -> set[str]:
    state = _get_sim_state(db)
    if state is None:
        return set()
    try:
        return set(json.loads(state.applied_signal_ids))
    except (json.JSONDecodeError, TypeError):
        return set()


def _get_anchor_date(db: Session):
    from datetime import date
    state = _get_sim_state(db)
    if state is None or not state.anchor_date:
        return None
    return date.fromisoformat(state.anchor_date)


# ─── Intent handlers ──────────────────────────────────────────────────────────

def answer_next_commitment(db: Session, now: datetime) -> PersonalAnswer:
    """
    Returns next class or event after now.
    Includes: leave-by time, walking minutes, rain note.
    Sources: ["SOLAR schedule", "campus map"]
    """
    from app.core.config import settings
    from app.models.models import CalendarEvent, Signal

    user_id = settings.demo_user_id
    now_utc = _ensure_utc(now)
    now_naive = now_utc.replace(tzinfo=None) if now_utc else now

    scenario = _get_scenario(db)
    anchor = _get_anchor_date(db)

    # Collect class events
    events = (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.user_id == user_id,
            CalendarEvent.event_type == "class",
            CalendarEvent.end_at_utc > now_naive,
        )
        .order_by(CalendarEvent.start_at_utc)
        .all()
    )

    if not events:
        # Real mode: try any upcoming events
        events = (
            db.query(CalendarEvent)
            .filter(
                CalendarEvent.user_id == user_id,
                CalendarEvent.end_at_utc > now_naive,
            )
            .order_by(CalendarEvent.start_at_utc)
            .limit(1)
            .all()
        )

    if not events:
        return PersonalAnswer(
            answer="No upcoming classes or commitments found for today.",
            coverage="partial",
            sources=[{"text": "SOLAR schedule", "feed": "solar"}],
            intent="next_commitment",
        )

    next_ev = events[0]
    start_utc = _ensure_utc(next_ev.start_at_utc)
    start_local = start_utc.astimezone(_CAMPUS_TZ)

    location = next_ev.location_text or "location TBD"
    title = next_ev.title

    # Walk info from scenario
    walk_note = ""
    leave_by_note = ""
    if scenario and anchor:
        persona = scenario.get("persona", {})
        start_place = persona.get("start_place", "MEL")
        walking_minutes_map: dict[str, int] = {}
        for key, mins in scenario.get("walking_minutes", {}).items():
            a, b = key.split("-")
            walking_minutes_map[f"{a}-{b}"] = mins
            walking_minutes_map[f"{b}-{a}"] = mins

        # Determine building of next class
        rooms = {r["id"]: r for r in scenario.get("rooms", [])}
        room_id = location
        # Try to resolve room id from location_text
        actual_room_id = None
        for rid, rdata in rooms.items():
            if rdata.get("name", "") == location or rid == location:
                actual_room_id = rid
                break
        building_id = None
        if actual_room_id and actual_room_id in rooms:
            building_id = rooms[actual_room_id].get("building", "")
        elif actual_room_id and "-" in actual_room_id:
            building_id = actual_room_id.split("-")[0]

        if building_id:
            walk_key = f"{start_place}-{building_id}"
            walk_mins = walking_minutes_map.get(walk_key, 0)
            buffer = scenario.get("walking_buffer_minutes", 3)
            if walk_mins > 0:
                walk_note = f" It's a {walk_mins}-minute walk."
                from datetime import timedelta
                leave_by = start_utc - timedelta(minutes=walk_mins + buffer)
                leave_by_local = leave_by.astimezone(_CAMPUS_TZ)
                leave_by_note = f" Leave by {leave_by_local.strftime('%I:%M %p').lstrip('0')}."

    # Rain note: check for weather signal around the class time
    rain_note = ""
    if scenario:
        applied_ids = _get_applied_signal_ids(db)
        for sig in db.query(Signal).filter(Signal.feed == "weather", Signal.kind == "forecast_change").all():
            if sig.id in applied_ids:
                try:
                    wp = json.loads(sig.payload) if isinstance(sig.payload, str) else sig.payload
                except (json.JSONDecodeError, TypeError):
                    wp = {}
                if wp.get("condition") == "rain":
                    rain_note = " Rain is forecast — bring an umbrella."
                    break

    answer = (
        f"Your next commitment is {title} at {_fmt_time(start_utc)}, "
        f"in {location}.{leave_by_note}{walk_note}{rain_note}"
    )

    return PersonalAnswer(
        answer=answer,
        coverage="supported",
        sources=[
            {"text": "SOLAR schedule", "feed": "solar"},
            {"text": "campus map", "feed": "campus_map"},
        ],
        intent="next_commitment",
    )


def answer_what_changed(db: Session, now: datetime) -> PersonalAnswer:
    """
    Returns list of applied relevant signals that affected the student, with times and reasons.
    """
    from app.models.models import Signal

    scenario = _get_scenario(db)
    if scenario is None:
        return PersonalAnswer(
            answer="No scenario is running. I can't see today's changes without a loaded schedule.",
            coverage="partial",
            sources=[],
            intent="what_changed",
        )

    applied_ids = _get_applied_signal_ids(db)

    interesting_kinds = {"room_change", "announcement", "event_rescheduled", "forecast_change"}
    sigs = (
        db.query(Signal)
        .filter(Signal.relevance == "relevant")
        .order_by(Signal.at_utc)
        .all()
    )

    changes = []
    for sig in sigs:
        if sig.id not in applied_ids:
            continue
        if sig.kind not in interesting_kinds:
            continue
        at = _ensure_utc(sig.at_utc)
        time_str = _fmt_time(at)
        changes.append(f"{time_str} — {sig.summary} ({sig.feed} feed)")

    if not changes:
        return PersonalAnswer(
            answer="No relevant changes have been applied to your schedule today.",
            coverage="supported",
            sources=[{"text": "SOLAR schedule", "feed": "solar"}],
            intent="what_changed",
        )

    answer = "Here's what changed today:\n" + "\n".join(f"• {c}" for c in changes)
    return PersonalAnswer(
        answer=answer,
        coverage="supported",
        sources=[
            {"text": "SOLAR schedule", "feed": "solar"},
            {"text": "campus events feed", "feed": "campus_events"},
        ],
        intent="what_changed",
    )


def answer_why_moved(db: Session, question: str, now: datetime) -> PersonalAnswer:
    """Extract the room or class mentioned; find the signal that moved it; return its reason."""
    from app.models.models import Signal

    scenario = _get_scenario(db)
    if scenario is None:
        return PersonalAnswer(
            answer="No scenario is running. I can't look up move history without a loaded schedule.",
            coverage="partial",
            sources=[],
            intent="why_moved",
        )

    applied_ids = _get_applied_signal_ids(db)

    # Find room_change signals
    sigs = (
        db.query(Signal)
        .filter(Signal.kind == "room_change", Signal.relevance == "relevant")
        .order_by(Signal.at_utc.desc())
        .all()
    )

    q_lower = question.lower()
    matched_sig = None

    # Try to match by course or room mentioned in question
    for sig in sigs:
        if sig.id not in applied_ids:
            continue
        try:
            payload = json.loads(sig.payload) if isinstance(sig.payload, str) else sig.payload
        except (json.JSONDecodeError, TypeError):
            payload = {}
        commitment_id = payload.get("commitment", "")
        # Find commitment to get course label
        for c in scenario.get("commitments", []):
            if c["id"] == commitment_id:
                course_lower = c.get("course", "").lower()
                title_lower = c.get("title", "").lower()
                if any(word in q_lower for word in course_lower.split() + title_lower.split()[:2]):
                    matched_sig = (sig, payload, c)
                    break
        if matched_sig:
            break

    # If no specific match, return the most recent room change
    if not matched_sig and sigs:
        for sig in sigs:
            if sig.id not in applied_ids:
                continue
            try:
                payload = json.loads(sig.payload) if isinstance(sig.payload, str) else sig.payload
            except (json.JSONDecodeError, TypeError):
                payload = {}
            commitment_id = payload.get("commitment", "")
            for c in scenario.get("commitments", []):
                if c["id"] == commitment_id:
                    matched_sig = (sig, payload, c)
                    break
            if matched_sig:
                break

    if not matched_sig:
        return PersonalAnswer(
            answer="I couldn't find a room change matching your question.",
            coverage="not_found",
            sources=[],
            intent="why_moved",
        )

    sig, payload, commitment = matched_sig
    reason = payload.get("reason", "No reason recorded.")
    from_room = payload.get("from", "the previous room")
    to_room_id = payload.get("to", "")
    rooms = {r["id"]: r for r in scenario.get("rooms", [])}
    to_room_name = rooms.get(to_room_id, {}).get("name", to_room_id) if to_room_id else "unknown"

    answer = (
        f"{commitment['title']} was moved from {from_room} to {to_room_name}. "
        f"Reason: {reason}"
    )
    return PersonalAnswer(
        answer=answer,
        coverage="supported",
        sources=[{"text": "SOLAR schedule", "feed": "solar"}],
        intent="why_moved",
    )


def answer_time_to_finish(db: Session, now: datetime) -> PersonalAnswer:
    """
    Find the most urgent open task (by due date).
    Remaining estimated minutes vs scheduled aurora_block minutes.
    Available free windows tonight.
    """
    from app.core.config import settings
    from app.models.models import CalendarEvent, Task

    user_id = settings.demo_user_id
    now_utc = _ensure_utc(now)
    now_naive = now_utc.replace(tzinfo=None) if now_utc else now

    # Find most urgent open task due today or soonest
    tasks = (
        db.query(Task)
        .filter(Task.user_id == user_id, Task.status != "done")
        .order_by(Task.due_at_utc)
        .all()
    )

    if not tasks:
        return PersonalAnswer(
            answer="You have no open tasks.",
            coverage="supported",
            sources=[{"text": "Brightspace tasks", "feed": "brightspace"}],
            intent="time_to_finish",
        )

    task = tasks[0]
    est = task.estimated_minutes
    title = task.title

    # Planned minutes in aurora_blocks for this task
    planned_mins = 0
    aurora_blocks = (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.user_id == user_id,
            CalendarEvent.source_type == "aurora_block",
        )
        .all()
    )
    for blk in aurora_blocks:
        if task.id in (blk.source_reference or ""):
            start = _ensure_utc(blk.start_at_utc)
            end = _ensure_utc(blk.end_at_utc)
            if start and end:
                planned_mins += int((end - start).total_seconds() / 60)

    remaining = max(0, est - planned_mins)

    # Free windows tonight: use world if available, else simple heuristic
    from datetime import timedelta
    scenario = _get_scenario(db)
    free_window_note = ""

    if scenario:
        from app.services.campus.world import build_world
        world = build_world(db)
        if world:
            windows = world.free_windows(now)
            tonight_windows = [
                w for w in windows
                if w[0].astimezone(_CAMPUS_TZ).hour >= 17  # 5 PM+
            ]
            if tonight_windows:
                w = tonight_windows[0]
                w_start = w[0].astimezone(_CAMPUS_TZ)
                w_end = w[1].astimezone(_CAMPUS_TZ)
                w_mins = int((w[1] - w[0]).total_seconds() / 60)
                free_window_note = (
                    f" One free window tonight: "
                    f"{w_start.strftime('%I:%M %p').lstrip('0')} – "
                    f"{w_end.strftime('%I:%M %p').lstrip('0')} ({w_mins} min)."
                )

    if remaining <= 0:
        answer = f"{title}: {est} min estimated, {planned_mins} min already planned. You're on track!"
    elif planned_mins > 0:
        answer = (
            f"{title}: {est} min estimated, {planned_mins} min already planned. "
            f"You need {remaining} more minutes.{free_window_note}"
        )
    else:
        answer = (
            f"{title}: {est} min estimated, none planned yet. "
            f"You need {remaining} more minutes.{free_window_note}"
        )

    due_note = ""
    if task.due_at_utc:
        due_utc = _ensure_utc(task.due_at_utc)
        due_note = f" Due: {_fmt_time(due_utc)}."
        answer += due_note

    return PersonalAnswer(
        answer=answer,
        coverage="supported",
        sources=[
            {"text": "Brightspace tasks", "feed": "brightspace"},
            {"text": "AURORA study plan", "feed": "aurora_block"},
        ],
        intent="time_to_finish",
    )


def answer_room_status(db: Session, question: str, now: datetime) -> PersonalAnswer:
    """Look for a building_ops incident signal matching the room/building mentioned."""
    from app.models.models import Signal

    scenario = _get_scenario(db)
    if scenario is None:
        return PersonalAnswer(
            answer="No scenario is running. I can't check room status without a loaded schedule.",
            coverage="partial",
            sources=[],
            intent="room_status",
        )

    applied_ids = _get_applied_signal_ids(db)
    q_lower = question.lower()

    incident_sigs = (
        db.query(Signal)
        .filter(Signal.feed == "building_ops", Signal.kind == "incident")
        .order_by(Signal.at_utc.desc())
        .all()
    )

    rooms = {r["id"]: r for r in scenario.get("rooms", [])}

    matched = None
    for sig in incident_sigs:
        if sig.id not in applied_ids:
            continue
        try:
            payload = json.loads(sig.payload) if isinstance(sig.payload, str) else sig.payload
        except (json.JSONDecodeError, TypeError):
            payload = {}
        room_id = payload.get("room", "")
        room_data = rooms.get(room_id, {})
        room_name = room_data.get("name", room_id).lower()
        # Check if question mentions this room or building
        if any(part in q_lower for part in room_name.split() + [room_id.lower()]):
            matched = (sig, payload, room_id)
            break

    if not matched:
        # Return first incident if any
        for sig in incident_sigs:
            if sig.id not in applied_ids:
                continue
            try:
                payload = json.loads(sig.payload) if isinstance(sig.payload, str) else sig.payload
            except (json.JSONDecodeError, TypeError):
                payload = {}
            room_id = payload.get("room", "")
            matched = (sig, payload, room_id)
            break

    if not matched:
        return PersonalAnswer(
            answer="No active room incidents found.",
            coverage="supported",
            sources=[{"text": "Building operations", "feed": "building_ops"}],
            intent="room_status",
        )

    sig, payload, room_id = matched
    room_name = rooms.get(room_id, {}).get("name", room_id)
    temp = payload.get("temperature_c")
    trend = payload.get("trend", "")
    temp_note = f" Temperature: {temp}°C and {trend}." if temp else ""

    answer = f"{room_name} has an active HVAC incident.{temp_note} Facilities have been notified (simulated)."
    return PersonalAnswer(
        answer=answer,
        coverage="supported",
        sources=[{"text": "Building operations", "feed": "building_ops"}],
        intent="room_status",
    )


# ─── Main entry ───────────────────────────────────────────────────────────────

def answer_personal(db: Session, question: str, now: datetime) -> Optional[PersonalAnswer]:
    """
    Return a PersonalAnswer if intent matched, else None (caller falls back to public retriever).
    Handles real mode gracefully — returns partial/not_found for personal intents.
    """
    intent = match_intent(question)
    if intent is None:
        return None

    if intent == "next_commitment":
        return answer_next_commitment(db, now)
    elif intent == "what_changed":
        return answer_what_changed(db, now)
    elif intent == "why_moved":
        return answer_why_moved(db, question, now)
    elif intent == "time_to_finish":
        return answer_time_to_finish(db, now)
    elif intent == "room_status":
        return answer_room_status(db, question, now)

    return None

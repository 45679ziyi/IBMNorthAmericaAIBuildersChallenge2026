"""
AURORA Campus Intelligence — Action Execution Layer (M3)

Executes allowlisted actions on behalf of the user.
All "now" via get_now(). All external/simulated actions are labeled.

SAFETY NOTE: No send action exists. No smtp, no email dispatch, no push
notification, no requests.post. draft_message creates a local draft only.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.models.models import (
    ActionLog,
    AuditEvent,
    CalendarEvent,
    Reminder,
    Task,
)

# ─── Allowlist ────────────────────────────────────────────────────────────────

ALLOWLIST = {
    "create_calendar_block",
    "update_event_location",
    "create_task",
    "add_reminder",
    "book_room",            # simulated — no real booking
    "request_room_change",  # simulated — no real request sent
    "draft_message",        # draft only — never sent
}

# Actions that are simulated (no real external effect)
SIMULATED_TYPES = {"book_room", "request_room_change", "draft_message"}

# Actions that represent external systems (always simulated in this prototype)
EXTERNAL_TYPES = {"book_room", "request_room_change"}


# ─── Main entry point ─────────────────────────────────────────────────────────

def execute_action(db: Session, action: dict, move: Any) -> dict:
    """
    Execute one action from the allowlist.

    Args:
        db:     SQLAlchemy session
        action: dict with keys: id, type, params (from Move.actions JSON)
        move:   Move ORM object

    Returns:
        {"result": str, "simulated": bool, "undo_payload": dict}

    Raises:
        ValueError: if action type is not in ALLOWLIST
    """
    action_type = action.get("type", "")
    params = action.get("params", {})
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except (json.JSONDecodeError, TypeError):
            params = {}

    if action_type not in ALLOWLIST:
        raise ValueError(
            f"Action type '{action_type}' is not in the allowlist. "
            f"Allowed types: {sorted(ALLOWLIST)}"
        )

    simulated = action_type in SIMULATED_TYPES
    now = get_now()
    now_naive = now.replace(tzinfo=None) if now.tzinfo else now

    # Dispatch to handler
    handlers = {
        "create_calendar_block": _create_calendar_block,
        "update_event_location": _update_event_location,
        "create_task": _create_task,
        "add_reminder": _add_reminder,
        "book_room": _book_room,
        "request_room_change": _request_room_change,
        "draft_message": _draft_message,
    }

    result_data = handlers[action_type](db, params, move, now_naive)
    result_text = result_data["result"]
    undo_payload = result_data.get("undo_payload", {})

    # Determine status label for ActionLog
    if action_type == "draft_message":
        status = "draft_only"
    elif simulated:
        status = "executed_simulated"
    else:
        status = "executed"

    # Write ActionLog row
    log = ActionLog(
        id=uuid.uuid4().hex,
        move_id=move.id,
        action_type=action_type,
        params=json.dumps(params),
        status=status,
        simulated=simulated,
        undo_payload=json.dumps(undo_payload),
        result_text=result_text,
        created_at=now_naive,
    )
    db.add(log)

    # Write AuditEvent
    audit = AuditEvent(
        id=str(uuid.uuid4()),
        user_id=None,
        action=f"execute_action:{action_type}",
        resource_type="move",
        resource_id=move.id,
        result="ok_simulated" if simulated else "ok",
        created_at_utc=now_naive,
    )
    db.add(audit)

    db.flush()

    return {
        "result": result_text,
        "simulated": simulated,
        "undo_payload": undo_payload,
        "action_log_id": log.id,
    }


# ─── Handlers ─────────────────────────────────────────────────────────────────

def _create_calendar_block(
    db: Session, params: dict, move: Any, now: datetime
) -> dict:
    """Insert a CalendarEvent with source_type='aurora_block'.

    D10 fix: reject creation if the new block overlaps an existing committed
    event (class or aurora_block) for the same user.
    """
    from app.core.config import settings

    title = params.get("title", "Study Block")
    start_str = params.get("start")
    end_str = params.get("end")
    location = params.get("location")

    start_utc = _parse_dt(start_str, now)
    end_utc = _parse_dt(end_str, now)

    # D10: Check for overlap with existing committed events
    overlap = _check_calendar_overlap(db, settings.demo_user_id, start_utc, end_utc)
    if overlap:
        raise ValueError(
            f"Cannot create block '{title}': overlaps existing commitment "
            f"'{overlap.title}' ({overlap.start_at_utc} – {overlap.end_at_utc})."
        )

    event = CalendarEvent(
        id=str(uuid.uuid4()),
        user_id=settings.demo_user_id,
        title=title,
        description=f"Aurora block for move {move.id}",
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        location_text=location,
        event_type="aurora_block",
        source_type="aurora_block",
        source_reference=move.id,
        last_synced_at=now,
    )
    db.add(event)
    db.flush()

    return {
        "result": f"Calendar block '{title}' created.",
        "undo_payload": {"delete_event_id": event.id},
    }


def _check_calendar_overlap(
    db: Session, user_id: str, start_utc: datetime, end_utc: datetime
) -> "CalendarEvent | None":
    """Return the first overlapping hard commitment, or None.

    D10: Only checks against class events (event_type='class') and aurora_blocks.
    Saved events (event_type='other') and personal events are NOT hard commitments
    and must not block aurora_block creation.
    A block that touches but does not overlap (end == other_start) is allowed.
    """
    start_naive = start_utc.replace(tzinfo=None) if start_utc.tzinfo else start_utc
    end_naive = end_utc.replace(tzinfo=None) if end_utc.tzinfo else end_utc

    return (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.user_id == user_id,
            CalendarEvent.event_type.in_(["class", "aurora_block"]),
            CalendarEvent.start_at_utc < end_naive,
            CalendarEvent.end_at_utc > start_naive,
        )
        .first()
    )


def _update_event_location(
    db: Session, params: dict, move: Any, now: datetime
) -> dict:
    """Update a CalendarEvent's location_text."""
    event_id = params.get("event_id")
    new_location = params.get("location", "")

    if not event_id:
        return {
            "result": "No event_id specified; location not updated.",
            "undo_payload": {},
        }

    event = db.get(CalendarEvent, event_id)
    if event is None:
        return {
            "result": f"Event {event_id} not found; location not updated.",
            "undo_payload": {},
        }

    old_location = event.location_text or ""
    event.location_text = new_location
    db.flush()

    return {
        "result": f"Location updated from '{old_location}' to '{new_location}'.",
        "undo_payload": {"event_id": event_id, "old_location": old_location},
    }


def _create_task(
    db: Session, params: dict, move: Any, now: datetime
) -> dict:
    """Insert a Task row from the action params."""
    from app.core.config import settings

    title = params.get("title", "New Task")
    course = params.get("course", "")
    due_str = params.get("due_at")
    est_minutes = int(params.get("est_minutes", 60))
    source_signal_id = params.get("source_signal_id")

    # Determine provenance from params hint or default to "announcement"
    provenance = params.get("provenance", "announcement")

    due_utc = _parse_dt(due_str, now) if due_str else None

    task = Task(
        id=str(uuid.uuid4()),
        user_id=settings.demo_user_id,
        title=title,
        course_label=course or None,
        due_at_utc=due_utc,
        estimated_minutes=est_minutes,
        priority="normal",
        status="todo",
        source_type="approved_connector",
        source_signal_id=source_signal_id,
        provenance=provenance,
        created_at=now,
        updated_at=now,
    )
    db.add(task)
    db.flush()

    return {
        "result": f"Task '{title}' created.",
        "undo_payload": {"delete_task_id": task.id},
    }


def _add_reminder(
    db: Session, params: dict, move: Any, now: datetime
) -> dict:
    """Insert a Reminder row."""
    text = params.get("text", "Reminder")
    at_str = params.get("at_utc") or params.get("at")
    at_utc = _parse_dt(at_str, now) if at_str else now
    scenario_id = getattr(move, "scenario_id", None)

    reminder = Reminder(
        id=str(uuid.uuid4()),
        text=text,
        at_utc=at_utc,
        fired=False,
        move_id=move.id,
        scenario_id=scenario_id,
    )
    db.add(reminder)
    db.flush()

    return {
        "result": f"Reminder '{text}' set.",
        "undo_payload": {"delete_reminder_id": reminder.id},
    }


def _book_room(
    db: Session, params: dict, move: Any, now: datetime
) -> dict:
    """Simulated room booking — no real booking is made."""
    room_id = params.get("room_id", "unknown")

    log_id = uuid.uuid4().hex
    # The ActionLog is written by the caller (execute_action), so we just return
    # a placeholder undo_payload referencing the log that will be created.
    # We use a pre-generated ID here and pass it back.
    return {
        "result": "Simulated: no booking was made.",
        "undo_payload": {"delete_action_log_id": "__self__"},
    }


def _request_room_change(
    db: Session, params: dict, move: Any, now: datetime
) -> dict:
    """Simulated room change request.

    D4 fix: actually update the CalendarEvent's location so the commitment
    moves to the new room. This ensures that after approval, subsequent
    evaluate() calls see the class in the new room and the ops_impact
    detector no longer generates a new proposed move for the same incident.
    The move stays terminal (executed_simulated) and is not re-proposed.
    """
    commitment_id = params.get("commitment_id")
    proposed_room = params.get("proposed_room")
    proposed_room_name = params.get("proposed_room_name", proposed_room)
    old_room = params.get("current_room", "unknown")

    result_text = "Simulated: no room change request was sent."

    if commitment_id and proposed_room:
        from app.core.config import settings as _settings
        event = (
            db.query(CalendarEvent)
            .filter(
                CalendarEvent.user_id == _settings.demo_user_id,
                CalendarEvent.source_reference == commitment_id,
            )
            .first()
        )
        if event:
            event.location_text = proposed_room_name or proposed_room
            db.flush()
            result_text = (
                f"Simulated: room change applied — class moved from {old_room} "
                f"to {proposed_room_name or proposed_room}."
            )

    return {
        "result": result_text,
        "undo_payload": {
            "restore_room_commitment_id": commitment_id,
            "old_room_name": old_room,
        },
    }


def _draft_message(
    db: Session, params: dict, move: Any, now: datetime
) -> dict:
    """Create a local draft — never sent automatically."""
    subject = params.get("subject", "(no subject)")
    return {
        "result": "Draft created. Not sent.",
        "undo_payload": {"delete_action_log_id": "__self__"},
    }


# ─── Undo ─────────────────────────────────────────────────────────────────────

def undo_action(db: Session, action_log_id: str) -> dict:
    """
    Apply the inverse of a previously executed action.
    Sets action_log.status = 'undone'.
    Returns {"status": "undone", "message": str}.
    """
    log = db.get(ActionLog, action_log_id)
    if log is None:
        raise ValueError(f"ActionLog {action_log_id} not found.")
    if log.status == "undone":
        return {"status": "undone", "message": "Already undone."}

    try:
        payload = json.loads(log.undo_payload) if log.undo_payload else {}
    except (json.JSONDecodeError, TypeError):
        payload = {}

    message = _apply_undo(db, payload, log)

    log.status = "undone"
    now = get_now()
    now_naive = now.replace(tzinfo=None) if now.tzinfo else now

    # Audit the undo
    audit = AuditEvent(
        id=str(uuid.uuid4()),
        user_id=None,
        action=f"undo_action:{log.action_type}",
        resource_type="action_log",
        resource_id=log.id,
        result="ok",
        created_at_utc=now_naive,
    )
    db.add(audit)
    db.flush()

    return {"status": "undone", "message": message}


def _apply_undo(db: Session, payload: dict, log: ActionLog) -> str:
    """Dispatch undo payload to the right inverse operation."""
    if "delete_event_id" in payload:
        event_id = payload["delete_event_id"]
        event = db.get(CalendarEvent, event_id)
        if event:
            db.delete(event)
            return f"Calendar event {event_id} deleted."
        return f"Calendar event {event_id} not found (already deleted?)."

    if "delete_task_id" in payload:
        task_id = payload["delete_task_id"]
        task = db.get(Task, task_id)
        if task:
            db.delete(task)
            return f"Task {task_id} deleted."
        return f"Task {task_id} not found (already deleted?)."

    if "delete_reminder_id" in payload:
        reminder_id = payload["delete_reminder_id"]
        reminder = db.get(Reminder, reminder_id)
        if reminder:
            db.delete(reminder)
            return f"Reminder {reminder_id} deleted."
        return f"Reminder {reminder_id} not found (already deleted?)."

    if "event_id" in payload and "old_location" in payload:
        event = db.get(CalendarEvent, payload["event_id"])
        if event:
            event.location_text = payload["old_location"]
            return f"Location restored to '{payload['old_location']}'."
        return f"Event {payload['event_id']} not found."

    if "restore_room_commitment_id" in payload:
        # D4: undo a request_room_change by restoring the old room name
        from app.core.config import settings as _settings
        commitment_id = payload["restore_room_commitment_id"]
        old_room_name = payload.get("old_room_name", "")
        if commitment_id:
            event = (
                db.query(CalendarEvent)
                .filter(
                    CalendarEvent.user_id == _settings.demo_user_id,
                    CalendarEvent.source_reference == commitment_id,
                )
                .first()
            )
            if event:
                event.location_text = old_room_name
                return f"Room restored to '{old_room_name}' for commitment {commitment_id}."
        return f"Commitment {commitment_id} not found for room restore."

    if "delete_action_log_id" in payload:
        # For simulated/draft actions: the log itself is the artifact
        return f"Simulated action {log.id} marked undone (no real system change to reverse)."

    return "Undo: no reversible payload found."


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_dt(value: str | None, fallback: datetime) -> datetime:
    """Parse an ISO datetime string or return fallback. Always naive (UTC)."""
    if not value:
        return fallback
    try:
        dt = datetime.fromisoformat(value)
        # Strip timezone info — store naive UTC in DB
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return fallback

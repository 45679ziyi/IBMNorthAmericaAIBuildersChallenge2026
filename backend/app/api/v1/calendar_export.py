"""
Calendar ICS export endpoint (M3)

GET /calendar/aurora.ics → text/calendar
Returns a read-only ICS file of all CalendarEvent rows with source_type="aurora_block".
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytz
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.tenancy import ActorContext, resolve_actor, current_user_id
from app.db.session import get_db
from app.models.models import CalendarEvent

router = APIRouter()

_CAMPUS_TZ = pytz.timezone("America/New_York")
_TZID = "America/New_York"


def _dt_to_ics(dt: datetime) -> str:
    """
    Convert a UTC (possibly naive) datetime to a local wall-clock ICS string.
    Format: TZID=America/New_York:YYYYMMDDTHHmmss
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    local = dt.astimezone(_CAMPUS_TZ)
    return local.strftime("%Y%m%dT%H%M%S")


def _escape_ics(text: str) -> str:
    """Escape ICS text values (RFC 5545 §3.3.11)."""
    return (
        text.replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n")
    )


@router.get("/aurora.ics", response_class=PlainTextResponse)
def export_aurora_ics(
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """
    Export all aurora_block CalendarEvents as a standards-compliant ICS feed.
    Content-Type: text/calendar
    """
    user_id = current_user_id(actor)
    events = (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.user_id == user_id,
            CalendarEvent.source_type == "aurora_block",
        )
        .order_by(CalendarEvent.start_at_utc)
        .all()
    )

    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//AURORA Campus Intelligence//EN",
        "X-WR-CALNAME:AURORA Blocks",
        f"X-WR-TIMEZONE:{_TZID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for event in events:
        dtstart = _dt_to_ics(event.start_at_utc)
        dtend = _dt_to_ics(event.end_at_utc)
        uid = f"{event.id}@aurora"
        summary = _escape_ics(event.title or "AURORA Block")
        description = _escape_ics(event.location_text or "")

        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{uid}")
        lines.append(f"SUMMARY:{summary}")
        lines.append(f"DTSTART;TZID={_TZID}:{dtstart}")
        lines.append(f"DTEND;TZID={_TZID}:{dtend}")
        if description:
            lines.append(f"DESCRIPTION:{description}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")

    ics_content = "\r\n".join(lines) + "\r\n"
    return PlainTextResponse(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="aurora.ics"'},
    )

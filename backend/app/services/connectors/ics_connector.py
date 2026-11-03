"""ICS calendar file connector — parse .ics files into CalendarEvent ORM objects."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from typing import Any

import pytz
from icalendar import Calendar, Event as ICalEvent  # type: ignore
from dateutil.rrule import rruleset, rrulestr

from app.models.models import CalendarEvent


@dataclass
class ICSParseResult:
    imported: int
    skipped: int
    warnings: list[str]
    events: list[CalendarEvent]


def parse_ics_file(raw_bytes: bytes, user_id: str) -> ICSParseResult:
    """Parse raw ICS bytes and return normalized CalendarEvent objects."""
    warnings: list[str] = []
    events: list[CalendarEvent] = []
    skipped = 0

    try:
        cal = Calendar.from_ical(raw_bytes)
    except Exception as exc:
        return ICSParseResult(
            imported=0,
            skipped=0,
            warnings=[f"Could not parse ICS file: {exc}"],
            events=[],
        )

    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        try:
            event = _parse_vevent(component, user_id, warnings)
            if event:
                events.append(event)
            else:
                skipped += 1
        except Exception as exc:
            warnings.append(f"Skipped event: {exc}")
            skipped += 1

    return ICSParseResult(imported=len(events), skipped=skipped, warnings=warnings, events=events)


def _to_utc(dt_val: Any) -> datetime | None:
    """Convert a date or datetime from icalendar to UTC-aware datetime."""
    if dt_val is None:
        return None
    if isinstance(dt_val, datetime):
        if dt_val.tzinfo is None:
            # Assume Eastern time for naive datetimes
            eastern = pytz.timezone("America/New_York")
            dt_val = eastern.localize(dt_val)
        return dt_val.astimezone(timezone.utc)
    if isinstance(dt_val, date):
        # All-day events — treat as midnight Eastern
        eastern = pytz.timezone("America/New_York")
        dt_aware = eastern.localize(datetime(dt_val.year, dt_val.month, dt_val.day))
        return dt_aware.astimezone(timezone.utc)
    return None


def _parse_vevent(component: Any, user_id: str, warnings: list[str]) -> CalendarEvent | None:
    title = str(component.get("SUMMARY", "Untitled event")).strip()
    description = str(component.get("DESCRIPTION", "") or "").strip() or None
    location_text = str(component.get("LOCATION", "") or "").strip()[:256] or None

    dtstart = component.get("DTSTART")
    dtend = component.get("DTEND")

    if dtstart is None:
        warnings.append(f"Event '{title}' has no DTSTART; skipped.")
        return None

    start_utc = _to_utc(dtstart.dt if hasattr(dtstart, "dt") else dtstart)
    end_utc = _to_utc(dtend.dt if (dtend and hasattr(dtend, "dt")) else (dtend if dtend else None))

    if start_utc is None:
        warnings.append(f"Event '{title}': could not parse start time; skipped.")
        return None

    if end_utc is None or end_utc <= start_utc:
        # Default 1-hour duration
        from datetime import timedelta
        end_utc = start_utc + timedelta(hours=1)
        warnings.append(f"Event '{title}': end time missing or invalid; defaulted to 1 hour.")

    return CalendarEvent(
        user_id=user_id,
        title=title[:256],
        description=description,
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        location_text=location_text,
        event_type="other",
        source_type="ics_import",
        source_reference=None,
    )

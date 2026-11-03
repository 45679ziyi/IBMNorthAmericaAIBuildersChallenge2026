"""Calendar events CRUD + ICS import endpoints."""
from __future__ import annotations

import io
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import CalendarEvent
from app.schemas.schemas import CalendarEventCreate, CalendarEventRead, CalendarEventUpdate, ICSImportResponse
from app.services.connectors.ics_connector import parse_ics_file
from app.core.config import settings

router = APIRouter()

MAX_ICS_BYTES = 2 * 1024 * 1024  # 2 MB


def _get_demo_user_id() -> str:
    return settings.demo_user_id


@router.get("", response_model=list[CalendarEventRead])
def list_events(db: Session = Depends(get_db)):
    user_id = _get_demo_user_id()
    return db.query(CalendarEvent).filter(CalendarEvent.user_id == user_id).all()


@router.post("", response_model=CalendarEventRead, status_code=status.HTTP_201_CREATED)
def create_event(payload: CalendarEventCreate, db: Session = Depends(get_db)):
    user_id = _get_demo_user_id()
    if payload.end_at_utc <= payload.start_at_utc:
        raise HTTPException(400, "end_at_utc must be after start_at_utc")
    event = CalendarEvent(user_id=user_id, **payload.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.put("/{event_id}", response_model=CalendarEventRead)
def update_event(event_id: str, payload: CalendarEventUpdate, db: Session = Depends(get_db)):
    event = db.get(CalendarEvent, event_id)
    if not event or event.user_id != _get_demo_user_id():
        raise HTTPException(404, "Event not found")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(event, k, v)
    db.commit()
    db.refresh(event)
    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: str, db: Session = Depends(get_db)):
    event = db.get(CalendarEvent, event_id)
    if not event or event.user_id != _get_demo_user_id():
        raise HTTPException(404, "Event not found")
    db.delete(event)
    db.commit()


@router.post("/import/ics", response_model=ICSImportResponse)
async def import_ics(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".ics"):
        raise HTTPException(400, "Only .ics files are accepted")
    raw = await file.read()
    if len(raw) > MAX_ICS_BYTES:
        raise HTTPException(400, f"File exceeds 2 MB limit ({len(raw)} bytes)")
    user_id = _get_demo_user_id()
    result = parse_ics_file(raw, user_id)
    for ev in result.events:
        db.add(ev)
    db.commit()
    for ev in result.events:
        db.refresh(ev)
    return ICSImportResponse(
        imported=result.imported,
        skipped=result.skipped,
        warnings=result.warnings,
        events=[CalendarEventRead.model_validate(e) for e in result.events],
    )

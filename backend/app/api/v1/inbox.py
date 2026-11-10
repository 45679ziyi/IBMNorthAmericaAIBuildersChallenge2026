"""Inbox API — U4.

Routes:
  GET  /inbox                   → list notifications (unread first)
  POST /inbox/{id}/read         → mark notification read
  POST /inbox/{id}/ack          → mark notification acknowledged
  GET  /inbox/preferences       → list notification prefs
  PUT  /inbox/preferences       → update prefs (upsert)
  GET  /inbox/unread-count      → {unread: int} derived from notifications table
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.core.tenancy import ActorContext, resolve_actor
from app.db.session import get_db
from app.models.models import AccessLog, Notification, NotificationPref

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class WhyEntry(BaseModel):
    rel: str
    entity_type: str
    entity_id: str
    text: str


class NotificationRead(BaseModel):
    id: str
    canonical_event_id: Optional[str]
    work_item_id: Optional[str]
    recipient_person_id: str
    kind: str
    title: str
    body: str
    why: list[WhyEntry]
    state: str
    requires_ack: bool
    data_origin: str
    created_at: datetime
    read_at: Optional[datetime]

    model_config = {"from_attributes": True}


class NotificationPrefRead(BaseModel):
    id: str
    person_id: str
    category: str
    enabled: bool

    model_config = {"from_attributes": True}


class NotificationPrefUpdate(BaseModel):
    category: str
    enabled: bool


class UnreadCount(BaseModel):
    unread: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _n_to_read(n: Notification) -> NotificationRead:
    try:
        why_raw = json.loads(n.why_json or "[]")
    except (json.JSONDecodeError, TypeError):
        why_raw = []
    why = [WhyEntry(**w) if isinstance(w, dict) else w for w in why_raw]
    return NotificationRead(
        id=n.id,
        canonical_event_id=n.canonical_event_id,
        work_item_id=n.work_item_id,
        recipient_person_id=n.recipient_person_id,
        kind=n.kind,
        title=n.title,
        body=n.body,
        why=why,
        state=n.state,
        requires_ack=n.requires_ack,
        data_origin=n.data_origin,
        created_at=n.created_at,
        read_at=n.read_at,
    )


def _write_access_log(
    db: Session,
    actor: ActorContext,
    purpose: str,
    resource_type: str,
    record_count: int = 0,
    canonical_event_id: Optional[str] = None,
) -> None:
    db.add(AccessLog(
        actor_id=actor.actor_id,
        actor_role=actor.role,
        purpose=purpose,
        resource_type=resource_type,
        record_count=record_count,
        canonical_event_id=canonical_event_id,
        created_at=get_now(),
    ))


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[NotificationRead])
def list_inbox(
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """List notifications for the current actor (unread first)."""
    notifs = (
        db.query(Notification)
        .filter(Notification.recipient_person_id == actor.actor_id)
        .order_by(
            Notification.state == "unread",  # True sorts last in SQL, so DESC needed
            Notification.created_at.desc(),
        )
        .all()
    )
    # Sort: unread first, then by created_at desc
    notifs.sort(key=lambda n: (0 if n.state == "unread" else 1, ))
    _write_access_log(db, actor, "inbox_view", "notification", len(notifs))
    db.commit()
    return [_n_to_read(n) for n in notifs]


@router.get("/unread-count", response_model=UnreadCount)
def unread_count(
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Return count of unread notifications from the notifications table."""
    cnt = (
        db.query(func.count(Notification.id))
        .filter(
            Notification.recipient_person_id == actor.actor_id,
            Notification.state == "unread",
        )
        .scalar()
    ) or 0
    return UnreadCount(unread=cnt)


@router.post("/{notif_id}/read", response_model=NotificationRead)
def mark_read(
    notif_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Mark a notification as read."""
    n = db.get(Notification, notif_id)
    if n is None or n.recipient_person_id != actor.actor_id:
        raise HTTPException(status_code=404, detail="Notification not found.")
    if n.state == "unread":
        n.state = "read"
        n.read_at = get_now()
        db.commit()
        db.refresh(n)
    return _n_to_read(n)


@router.post("/{notif_id}/ack", response_model=NotificationRead)
def mark_ack(
    notif_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Mark a notification as acknowledged."""
    n = db.get(Notification, notif_id)
    if n is None or n.recipient_person_id != actor.actor_id:
        raise HTTPException(status_code=404, detail="Notification not found.")
    if n.state != "acknowledged":
        n.state = "acknowledged"
        if n.read_at is None:
            n.read_at = get_now()
        db.commit()
        db.refresh(n)
    return _n_to_read(n)


@router.get("/preferences", response_model=list[NotificationPrefRead])
def get_preferences(
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """List notification preferences for the current actor."""
    prefs = (
        db.query(NotificationPref)
        .filter(NotificationPref.person_id == actor.actor_id)
        .all()
    )
    return [NotificationPrefRead.model_validate(p) for p in prefs]


@router.put("/preferences", response_model=NotificationPrefRead)
def update_preferences(
    body: NotificationPrefUpdate,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Upsert a notification preference for the current actor."""
    pref = (
        db.query(NotificationPref)
        .filter(
            NotificationPref.person_id == actor.actor_id,
            NotificationPref.category == body.category,
        )
        .first()
    )
    if pref is None:
        pref = NotificationPref(
            person_id=actor.actor_id,
            category=body.category,
            enabled=body.enabled,
        )
        db.add(pref)
    else:
        pref.enabled = body.enabled
    db.commit()
    db.refresh(pref)
    return NotificationPrefRead.model_validate(pref)

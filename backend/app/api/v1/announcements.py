"""Announcements endpoint — demo adapter only.

U1: ActorContext injected; 403 for non-student roles.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.db.session import get_db
from app.models.models import Announcement
from app.schemas.schemas import AnnouncementRead, AnnouncementUpdate
from app.core.tenancy import ActorContext, resolve_actor, current_user_id
from app.services.authz import authorize

router = APIRouter()


def _to_read(r: Announcement) -> AnnouncementRead:
    d = AnnouncementRead.model_validate(r)
    d.is_demo = r.source_type == "demo"
    return d


def _require_ann_access(actor: ActorContext) -> str:
    d = authorize(actor, "read:own_announcements")
    if not d:
        raise HTTPException(status_code=403, detail={"reason_code": d.reason_code, "message": d.reason})
    return current_user_id(actor)


@router.get("", response_model=list[AnnouncementRead])
def list_announcements(
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    user_id = _require_ann_access(actor)
    rows = db.query(Announcement).filter(Announcement.user_id == user_id).all()
    return [_to_read(r) for r in rows]


@router.patch("/{announcement_id}", response_model=AnnouncementRead)
def update_announcement(
    announcement_id: str,
    body: AnnouncementUpdate,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    user_id = _require_ann_access(actor)
    ann = db.get(Announcement, announcement_id)
    if ann is None or ann.user_id != user_id:
        raise HTTPException(status_code=404, detail="Announcement not found")
    ann.is_read = body.is_read
    ann.read_at_utc = get_now() if body.is_read else None
    db.commit()
    db.refresh(ann)
    return _to_read(ann)


@router.post("/mark-all-read", response_model=list[AnnouncementRead])
def mark_all_read(
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    user_id = _require_ann_access(actor)
    now = get_now()
    rows = db.query(Announcement).filter(Announcement.user_id == user_id).all()
    for ann in rows:
        ann.is_read = True
        ann.read_at_utc = now
    db.commit()
    return [_to_read(r) for r in rows]


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    user_id = _require_ann_access(actor)
    count = (
        db.query(Announcement)
        .filter(Announcement.user_id == user_id, Announcement.is_read == False)
        .count()
    )
    return {"unread": count}

"""Announcements endpoint — demo adapter only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.db.session import get_db
from app.models.models import Announcement
from app.schemas.schemas import AnnouncementRead, AnnouncementUpdate
from app.core.config import settings

router = APIRouter()


def _to_read(r: Announcement) -> AnnouncementRead:
    d = AnnouncementRead.model_validate(r)
    d.is_demo = r.source_type == "demo"
    return d


@router.get("", response_model=list[AnnouncementRead])
def list_announcements(db: Session = Depends(get_db)):
    user_id = settings.demo_user_id
    rows = db.query(Announcement).filter(Announcement.user_id == user_id).all()
    return [_to_read(r) for r in rows]


@router.patch("/{announcement_id}", response_model=AnnouncementRead)
def update_announcement(
    announcement_id: str,
    body: AnnouncementUpdate,
    db: Session = Depends(get_db),
):
    ann = db.get(Announcement, announcement_id)
    if ann is None:
        raise HTTPException(status_code=404, detail="Announcement not found")
    ann.is_read = body.is_read
    ann.read_at_utc = get_now() if body.is_read else None
    db.commit()
    db.refresh(ann)
    return _to_read(ann)


@router.post("/mark-all-read", response_model=list[AnnouncementRead])
def mark_all_read(db: Session = Depends(get_db)):
    user_id = settings.demo_user_id
    now = get_now()
    rows = db.query(Announcement).filter(Announcement.user_id == user_id).all()
    for ann in rows:
        ann.is_read = True
        ann.read_at_utc = now
    db.commit()
    return [_to_read(r) for r in rows]


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db)):
    user_id = settings.demo_user_id
    count = (
        db.query(Announcement)
        .filter(Announcement.user_id == user_id, Announcement.is_read == False)
        .count()
    )
    return {"unread": count}

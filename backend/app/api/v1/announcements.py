"""Announcements endpoint — demo adapter only."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import Announcement
from app.schemas.schemas import AnnouncementRead
from app.core.config import settings

router = APIRouter()


@router.get("", response_model=list[AnnouncementRead])
def list_announcements(db: Session = Depends(get_db)):
    user_id = settings.demo_user_id
    rows = db.query(Announcement).filter(Announcement.user_id == user_id).all()
    result = []
    for r in rows:
        d = AnnouncementRead.model_validate(r)
        d.is_demo = r.source_type == "demo"
        result.append(d)
    return result

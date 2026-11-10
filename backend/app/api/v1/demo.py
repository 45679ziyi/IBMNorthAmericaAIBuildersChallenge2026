"""Demo data reset endpoint.

U1: uses ActorContext to resolve the correct user_id.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import (
    CalendarEvent, Task, Announcement, CampusEvent, DailyPlan, PlanBlock, SensorReading
)
from app.core.tenancy import ActorContext, resolve_actor, current_user_id

router = APIRouter()


@router.delete("/demo/reset", status_code=200)
def reset_demo_data(
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Clear all demo-sourced records and re-seed from fixtures."""
    user_id = current_user_id(actor)
    db.query(PlanBlock).filter(
        PlanBlock.daily_plan_id.in_(
            db.query(DailyPlan.id).filter(DailyPlan.user_id == user_id)
        )
    ).delete(synchronize_session=False)
    db.query(DailyPlan).filter(DailyPlan.user_id == user_id).delete()
    db.query(Announcement).filter(Announcement.user_id == user_id).delete()
    db.query(CalendarEvent).filter(
        CalendarEvent.user_id == user_id,
        CalendarEvent.source_type == "demo"
    ).delete()
    db.query(Task).filter(
        Task.user_id == user_id,
        Task.source_type == "demo"
    ).delete()
    db.query(CampusEvent).filter(CampusEvent.is_demo_data == True).delete()
    db.query(SensorReading).delete()
    db.commit()

    # Re-seed
    from scripts.seed_demo_data import seed
    seed(db, user_id)

    return {"status": "reset", "message": "Demo data restored to initial state."}


@router.delete("/user/data", status_code=200)
def delete_user_data(
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Delete all local prototype data for the current demo user."""
    user_id = current_user_id(actor)
    db.query(PlanBlock).filter(
        PlanBlock.daily_plan_id.in_(
            db.query(DailyPlan.id).filter(DailyPlan.user_id == user_id)
        )
    ).delete(synchronize_session=False)
    db.query(DailyPlan).filter(DailyPlan.user_id == user_id).delete()
    db.query(Announcement).filter(Announcement.user_id == user_id).delete()
    db.query(CalendarEvent).filter(CalendarEvent.user_id == user_id).delete()
    db.query(Task).filter(Task.user_id == user_id).delete()
    db.query(CampusEvent).delete()
    db.query(SensorReading).delete()
    db.commit()
    return {"status": "deleted", "message": "All local prototype data deleted."}

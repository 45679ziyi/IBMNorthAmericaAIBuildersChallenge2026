"""Daily planning endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import DailyPlan
from app.schemas.schemas import DailyPlanRead, PlanGenerateRequest
from app.services.planner.engine import generate_plan
from app.core.config import settings

router = APIRouter()


def _demo_user_id() -> str:
    return settings.demo_user_id


@router.post("/generate", response_model=DailyPlanRead)
def generate(payload: PlanGenerateRequest, db: Session = Depends(get_db)):
    return generate_plan(db, _demo_user_id(), payload.plan_date, payload.timezone)


@router.post("/{plan_id}/accept", response_model=DailyPlanRead)
def accept_plan(plan_id: str, db: Session = Depends(get_db)):
    plan = db.get(DailyPlan, plan_id)
    if not plan or plan.user_id != _demo_user_id():
        raise HTTPException(404, "Plan not found")
    if plan.status != "draft":
        raise HTTPException(400, f"Plan is already {plan.status}")
    plan.status = "accepted"
    db.commit()
    db.refresh(plan)
    return _plan_with_meta(plan)


@router.post("/{plan_id}/reject", response_model=DailyPlanRead)
def reject_plan(plan_id: str, db: Session = Depends(get_db)):
    plan = db.get(DailyPlan, plan_id)
    if not plan or plan.user_id != _demo_user_id():
        raise HTTPException(404, "Plan not found")
    if plan.status != "draft":
        raise HTTPException(400, f"Plan is already {plan.status}")
    plan.status = "rejected"
    db.commit()
    db.refresh(plan)
    return _plan_with_meta(plan)


def _plan_with_meta(plan: DailyPlan) -> DailyPlanRead:
    d = DailyPlanRead.model_validate(plan)
    return d

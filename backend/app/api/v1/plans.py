"""Daily planning endpoints.

U1: ActorContext injected; 403 for non-student roles.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import DailyPlan
from app.schemas.schemas import DailyPlanRead, PlanGenerateRequest
from app.services.planner.engine import generate_plan
from app.core.tenancy import ActorContext, resolve_actor, current_user_id
from app.services.authz import authorize

router = APIRouter()


def _require_plan_access(actor: ActorContext) -> str:
    d = authorize(actor, "read:own_plan")
    if not d:
        raise HTTPException(status_code=403, detail={"reason_code": d.reason_code, "message": d.reason})
    return current_user_id(actor)


@router.post("/generate", response_model=DailyPlanRead)
def generate(
    payload: PlanGenerateRequest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    user_id = _require_plan_access(actor)
    return generate_plan(db, user_id, payload.plan_date, payload.timezone)


@router.post("/{plan_id}/accept", response_model=DailyPlanRead)
def accept_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    user_id = _require_plan_access(actor)
    plan = db.get(DailyPlan, plan_id)
    if not plan or plan.user_id != user_id:
        raise HTTPException(404, "Plan not found")
    if plan.status != "draft":
        raise HTTPException(400, f"Plan is already {plan.status}")
    plan.status = "accepted"
    db.commit()
    db.refresh(plan)
    return _plan_with_meta(plan)


@router.post("/{plan_id}/reject", response_model=DailyPlanRead)
def reject_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    user_id = _require_plan_access(actor)
    plan = db.get(DailyPlan, plan_id)
    if not plan or plan.user_id != user_id:
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

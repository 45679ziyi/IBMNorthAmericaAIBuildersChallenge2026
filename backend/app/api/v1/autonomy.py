"""
Autonomy Policy API endpoints (M3)

GET /autonomy   → AutonomyResponse  (current policy + locked info)
PUT /autonomy   → AutonomyResponse  (update one category)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.schemas import AutonomyResponse, AutonomyUpdateRequest
from app.services.campus.autonomy import (
    LOCKED_CATEGORIES,
    PolicyLockError,
    get_policy,
    set_policy,
)

router = APIRouter()


@router.get("", response_model=AutonomyResponse)
def get_autonomy(db: Session = Depends(get_db)):
    """Return the current autonomy policy and which categories are locked."""
    policy = get_policy(db)
    return AutonomyResponse(
        policy=policy,
        locked=sorted(LOCKED_CATEGORIES),
    )


@router.put("", response_model=AutonomyResponse)
def update_autonomy(
    body: AutonomyUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Update one autonomy policy category.

    Returns HTTP 400 if the category is locked (simulated_external, message_drafts)
    and the requested value is 'auto'.
    """
    try:
        updated = set_policy(db, {body.category: body.value})
    except PolicyLockError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return AutonomyResponse(
        policy=updated,
        locked=sorted(LOCKED_CATEGORIES),
    )

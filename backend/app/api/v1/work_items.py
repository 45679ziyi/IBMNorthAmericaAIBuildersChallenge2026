"""Work items API — U3.

Routes:
  GET  /work-items                        → list, filtered by role scope
  GET  /work-items/{id}                   → single work item
  POST /work-items/{id}/transition        → advance workflow (409 on illegal)
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.tenancy import ActorContext, resolve_actor
from app.db.session import get_db
from app.models.models import WorkItem, WorkItemTransition
from app.services.workflows.engine import engine as wf_engine, TransitionRequest

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class WorkItemResponse(BaseModel):
    id: str
    canonical_event_id: Optional[str]
    workflow_type: str
    status: str
    version: int
    owner_person_id: Optional[str]
    assigned_team_id: Optional[str]
    tenant_id: str
    payload: dict
    required_next_fields: list[str]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class TransitionBody(BaseModel):
    action: str
    payload: dict = {}
    rationale: Optional[str] = None
    expected_version: Optional[int] = None


class TransitionResponse(BaseModel):
    work_item_id: str
    from_status: str
    to_status: str
    version: int
    transition_id: str


# ── Role → allowed workflow types ─────────────────────────────────────────────
# Defines which work item types a role can see/act on.

_ROLE_WORKFLOW_SCOPE: dict[str, list[str]] = {
    "student":      ["service_request"],
    "faculty":      ["course_update", "event_change", "service_request"],
    "facilities":   ["incident_response", "room_reassignment", "service_disruption", "service_request"],
    "it":           ["incident_response", "service_disruption", "service_request"],
    "academic_ops": ["course_update", "room_reassignment", "event_change", "service_request",
                     "incident_response", "service_disruption"],
    "org_organizer": ["event_change", "service_request"],
}


def _wi_to_dict(wi: WorkItem) -> dict:
    try:
        payload = json.loads(wi.payload_json or "{}")
    except (json.JSONDecodeError, TypeError):
        payload = {}
    try:
        required_next = json.loads(wi.required_next_fields_json or "[]")
    except (json.JSONDecodeError, TypeError):
        required_next = []
    return {
        "id": wi.id,
        "canonical_event_id": wi.canonical_event_id,
        "workflow_type": wi.workflow_type,
        "status": wi.status,
        "version": wi.version,
        "owner_person_id": wi.owner_person_id,
        "assigned_team_id": wi.assigned_team_id,
        "tenant_id": wi.tenant_id,
        "payload": payload,
        "required_next_fields": required_next,
        "created_at": wi.created_at.isoformat() if wi.created_at else None,
        "updated_at": wi.updated_at.isoformat() if wi.updated_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
def list_work_items(
    workflow_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    canonical_event_id: Optional[str] = Query(None),
    team: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """List work items filtered by the actor's role scope."""
    allowed_types = _ROLE_WORKFLOW_SCOPE.get(actor.role, [])

    q = db.query(WorkItem)
    if allowed_types:
        q = q.filter(WorkItem.workflow_type.in_(allowed_types))
    if workflow_type:
        if workflow_type not in allowed_types:
            return []
        q = q.filter(WorkItem.workflow_type == workflow_type)
    if status:
        q = q.filter(WorkItem.status == status)
    if canonical_event_id:
        q = q.filter(WorkItem.canonical_event_id == canonical_event_id)
    if team:
        # Map team name to workflow types
        team_types = {
            "facilities": ["incident_response", "room_reassignment"],
            "it": ["service_disruption", "incident_response"],
            "academic_ops": ["course_update", "room_reassignment", "event_change"],
        }
        t_types = team_types.get(team, [])
        if t_types:
            q = q.filter(WorkItem.workflow_type.in_(t_types))

    items = q.order_by(WorkItem.created_at.desc()).all()
    return [_wi_to_dict(wi) for wi in items]


@router.get("/{item_id}")
def get_work_item(
    item_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Get a single work item by ID."""
    wi = db.get(WorkItem, item_id)
    if wi is None:
        raise HTTPException(status_code=404, detail="Work item not found.")

    # Scope check
    allowed_types = _ROLE_WORKFLOW_SCOPE.get(actor.role, [])
    if wi.workflow_type not in allowed_types:
        raise HTTPException(
            status_code=403,
            detail={
                "reason_code": "SCOPE_DENIED",
                "message": (
                    f"Role '{actor.role}' does not have access to "
                    f"workflow type '{wi.workflow_type}'."
                ),
            },
        )

    return _wi_to_dict(wi)


@router.post("/{item_id}/transition")
def transition_work_item(
    item_id: str,
    body: TransitionBody,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Advance a work item's workflow state.

    Returns 409 on illegal transition (wrong state, role denied, version conflict).
    Returns 403 when actor's role is not allowed for this action.
    """
    wi = db.get(WorkItem, item_id)
    if wi is None:
        raise HTTPException(status_code=404, detail="Work item not found.")

    # Scope check: role must be allowed to see this workflow type at all
    allowed_types = _ROLE_WORKFLOW_SCOPE.get(actor.role, [])
    if wi.workflow_type not in allowed_types:
        raise HTTPException(
            status_code=403,
            detail={
                "reason_code": "SCOPE_DENIED",
                "message": (
                    f"Role '{actor.role}' does not have access to "
                    f"workflow type '{wi.workflow_type}'."
                ),
            },
        )

    from_status = wi.status

    req = TransitionRequest(
        action=body.action,
        payload=body.payload,
        rationale=body.rationale,
        expected_version=body.expected_version,
        actor_mode="human",
    )

    # engine.advance raises 409/403 on failure
    updated_wi = wf_engine.advance(db, wi, req, actor)
    db.commit()
    db.refresh(updated_wi)

    # Find the transition record we just wrote
    last_transition = (
        db.query(WorkItemTransition)
        .filter(WorkItemTransition.work_item_id == item_id)
        .order_by(WorkItemTransition.created_at.desc())
        .first()
    )

    return TransitionResponse(
        work_item_id=updated_wi.id,
        from_status=from_status,
        to_status=updated_wi.status,
        version=updated_wi.version,
        transition_id=last_transition.id if last_transition else "",
    )

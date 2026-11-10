"""Service Requests API — U4.

Routes:
  POST /service-requests              → create, auto-route to team, notify team
  GET  /service-requests              → list (requester + assigned team only)
  POST /service-requests/{id}/transition → status machine transition

Status machine:
  submitted → triaged → in_progress → resolved → closed

Routing: looks up EntityLink with rel="owner_team" for service_id.
Privacy: non-requester/non-team members get 404 (no information leakage).
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.core.tenancy import ActorContext, resolve_actor
from app.db.session import get_db
from app.models.models import (
    EntityLink,
    Notification,
    NotificationPref,
    ServiceRequest,
    Team,
    TeamMembership,
)

router = APIRouter()

# ── State machine ─────────────────────────────────────────────────────────────

_TRANSITIONS: dict[str, list[str]] = {
    "submitted": ["triaged"],
    "triaged": ["in_progress"],
    "in_progress": ["resolved"],
    "resolved": ["closed"],
    "closed": [],
}


def _can_transition(current: str, target: str) -> bool:
    return target in _TRANSITIONS.get(current, [])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ServiceRequestCreate(BaseModel):
    service_id: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=256)
    body: str = Field("", max_length=4000)
    data_origin: str = "synthetic"
    # V4-03 (Finding N): optional link to the triggering canonical event
    canonical_event_id: Optional[str] = Field(None, max_length=64)
    # tenant_id removed from client payload (V4-01 Finding F): tenant is
    # server-resolved from ActorContext.tenant_id.  Any client-supplied value
    # is ignored.


class ServiceRequestRead(BaseModel):
    id: str
    tenant_id: str
    requester_person_id: str
    service_id: str
    title: str
    body: str
    status: str
    assigned_team_id: Optional[str]
    canonical_event_id: Optional[str]  # V4-03
    version: int
    data_origin: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TransitionBody(BaseModel):
    target_status: str
    rationale: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _route_to_team(db: Session, service_id: str) -> Optional[str]:
    """Look up EntityLink with rel='owner_team' for the service."""
    link = (
        db.query(EntityLink)
        .filter(
            EntityLink.from_type == "service",
            EntityLink.from_id == service_id,
            EntityLink.rel == "owner_team",
        )
        .first()
    )
    return link.to_id if link else None


def _is_authorized(db: Session, sr: ServiceRequest, actor: ActorContext) -> bool:
    """True if actor is the requester or a member of the assigned team.

    V4-01 (Finding B): removed the role-wide supervisor fallback.
    A role alone does NOT grant access to every service request.
    Access requires explicit requester identity OR assigned-team membership.
    """
    if sr.requester_person_id == actor.actor_id:
        return True
    if sr.assigned_team_id:
        membership = (
            db.query(TeamMembership)
            .filter(
                TeamMembership.team_id == sr.assigned_team_id,
                TeamMembership.person_id == actor.actor_id,
            )
            .first()
        )
        if membership:
            return True
    return False


def _pref_enabled(db: Session, person_id: str, category: str) -> bool:
    """Check if notification preference is enabled (default True if no record)."""
    pref = (
        db.query(NotificationPref)
        .filter(
            NotificationPref.person_id == person_id,
            NotificationPref.category == category,
        )
        .first()
    )
    return pref.enabled if pref is not None else True


def _notify_team(db: Session, sr: ServiceRequest, team_id: str) -> None:
    """Create a notification for each team member."""
    members = (
        db.query(TeamMembership)
        .filter(TeamMembership.team_id == team_id)
        .all()
    )
    for m in members:
        if not _pref_enabled(db, m.person_id, "service_disruption"):
            continue
        db.add(Notification(
            recipient_person_id=m.person_id,
            kind="service_disruption",
            title=f"New service request: {sr.title}",
            body=f"Service: {sr.service_id}. Status: {sr.status}.",
            why_json=json.dumps([{
                "rel": "assigned_to",
                "entity_type": "team",
                "entity_id": team_id,
                "text": "Your team was auto-routed this request.",
            }]),
            state="unread",
            requires_ack=False,
            data_origin=sr.data_origin,
            created_at=get_now(),
        ))


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=ServiceRequestRead, status_code=status.HTTP_201_CREATED)
def create_service_request(
    body: ServiceRequestCreate,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Create a service request and auto-route it to the owning team."""
    # V4-01 (Finding F/H): tenant resolved from server context, not request body.
    tenant_id = actor.tenant_id
    team_id = _route_to_team(db, body.service_id)

    sr = ServiceRequest(
        tenant_id=tenant_id,
        requester_person_id=actor.actor_id,
        service_id=body.service_id,
        title=body.title,
        body=body.body,
        status="submitted",
        assigned_team_id=team_id,
        canonical_event_id=body.canonical_event_id,  # V4-03 Finding N
        version=1,
        data_origin=body.data_origin,
        created_at=get_now(),
        updated_at=get_now(),
    )
    db.add(sr)
    db.flush()

    # Notify assigned team members
    if team_id:
        _notify_team(db, sr, team_id)

    db.commit()
    db.refresh(sr)
    return ServiceRequestRead.model_validate(sr)


@router.get("", response_model=list[ServiceRequestRead])
def list_service_requests(
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """List service requests visible to the current actor.

    V4-01 (Finding B): Removed role-wide 'see all' for supervisor roles.
    All actors see only: requests they submitted OR requests assigned to a team
    they belong to.
    """
    from sqlalchemy import or_
    # Get team IDs the actor belongs to
    memberships = (
        db.query(TeamMembership)
        .filter(TeamMembership.person_id == actor.actor_id)
        .all()
    )
    team_ids = [m.team_id for m in memberships]

    query = db.query(ServiceRequest)
    results = (
        query.filter(
            or_(
                ServiceRequest.requester_person_id == actor.actor_id,
                ServiceRequest.assigned_team_id.in_(team_ids) if team_ids else False,
            )
        )
        .order_by(ServiceRequest.created_at.desc())
        .all()
    )
    return [ServiceRequestRead.model_validate(sr) for sr in results]


@router.post("/{sr_id}/transition", response_model=ServiceRequestRead)
def transition_service_request(
    sr_id: str,
    body: TransitionBody,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Transition a service request through its status machine.

    Returns 404 for unauthorized actors (no information leakage).
    Returns 409 for illegal transitions.
    """
    sr = db.get(ServiceRequest, sr_id)
    if sr is None or not _is_authorized(db, sr, actor):
        raise HTTPException(status_code=404, detail="Service request not found.")

    if not _can_transition(sr.status, body.target_status):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason_code": "illegal_transition",
                "message": f"Cannot transition from '{sr.status}' to '{body.target_status}'.",
            },
        )

    sr.status = body.target_status
    sr.version += 1
    sr.updated_at = get_now()
    db.commit()
    db.refresh(sr)
    return ServiceRequestRead.model_validate(sr)

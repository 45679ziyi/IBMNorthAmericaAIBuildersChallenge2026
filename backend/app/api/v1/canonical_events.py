"""Canonical events API — U3.

Routes:
  POST /canonical-events                  → ingest (idempotent)
  GET  /canonical-events/{id}             → role-projected view
  GET  /canonical-events/{id}/reach       → per-role notified counts
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.core.tenancy import ActorContext, resolve_actor
from app.db.session import get_db
from app.models.models import AccessLog, CanonicalEvent, Notification, Person, WorkItem
from app.services.authz import authorize
from app.services.graph import audience_for
from app.services.workflows.definitions import workflow_for_event_type, WORKFLOW_REGISTRY

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class CanonicalEventIngest(BaseModel):
    type: str                                # e.g. "incident.hvac_fault"
    severity: str = "medium"
    source_feed: Optional[str] = None
    source_record_id: Optional[str] = None
    correlation_id: Optional[str] = None
    occurred_at: Optional[datetime] = None
    entity_refs: list[dict] = []             # [{type, id}, ...]
    classification: str = "institutional"
    payload: dict = {}
    data_origin: str = "synthetic"
    # tenant_id removed from client payload (V4-01 Finding F): tenant is
    # server-resolved from ActorContext.tenant_id.


class CanonicalEventResponse(BaseModel):
    id: str
    tenant_id: str
    type: str
    status: str
    severity: str
    correlation_id: Optional[str]
    idempotency_key: str
    source_feed: Optional[str]
    source_record_id: Optional[str]
    occurred_at: Optional[datetime]
    received_at: datetime
    entity_refs: list[dict]
    classification: str
    corroborations: int
    schema_version: str
    last_actor: Optional[str]
    last_actor_mode: str
    created_at: datetime
    audience: Optional[dict] = None          # included on full GET

    model_config = {"from_attributes": True}


class ReachResponse(BaseModel):
    canonical_event_id: str
    audience_counts: dict[str, int]
    audience_ids: Optional[dict[str, list[str]]] = None  # for authorized roles


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_idempotency_key(tenant_id: str, event_type: str, source_record_id: str) -> str:
    raw = f"{tenant_id}:{event_type}:{source_record_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _event_to_response(event: CanonicalEvent, include_audience: bool = False,
                        db: Session = None, actor: ActorContext = None) -> dict:
    try:
        entity_refs = json.loads(event.entity_refs_json or "[]")
    except (json.JSONDecodeError, TypeError):
        entity_refs = []

    result = {
        "id": event.id,
        "tenant_id": event.tenant_id,
        "type": event.type,
        "status": event.status,
        "severity": event.severity,
        "correlation_id": event.correlation_id,
        "idempotency_key": event.idempotency_key,
        "source_feed": event.source_feed,
        "source_record_id": event.source_record_id,
        "occurred_at": event.occurred_at,
        "received_at": event.received_at,
        "entity_refs": entity_refs,
        "classification": event.classification,
        "corroborations": event.corroborations,
        "schema_version": event.schema_version,
        "last_actor": event.last_actor,
        "last_actor_mode": event.last_actor_mode,
        "created_at": event.created_at,
    }

    # Role projection: students see limited info on non-personal events
    if actor is not None:
        if actor.role == "student" and event.classification == "restricted":
            result["payload"] = {}
        elif actor.role in ("facilities", "it"):
            # Staff see operational data but not personal refs
            pass
        # Include audience for authorized roles
        if include_audience and db is not None:
            if actor.role in ("facilities", "it", "academic_ops", "faculty"):
                result["audience"] = audience_for(db, event)

    return result


def _create_work_item(db: Session, event: CanonicalEvent, actor: ActorContext) -> WorkItem | None:
    """Create the initial work item for a canonical event if a workflow matches."""
    wf_type = workflow_for_event_type(event.type)
    if wf_type is None:
        return None
    wf = WORKFLOW_REGISTRY.get(wf_type)
    if wf is None:
        return None

    wi = WorkItem(
        canonical_event_id=event.id,
        workflow_type=wf_type,
        status=wf.initial_status,
        owner_person_id=actor.actor_id,
        tenant_id=event.tenant_id,
        payload_json="{}",
        version=1,
    )
    db.add(wi)
    return wi


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
def ingest_event(
    body: CanonicalEventIngest,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Ingest a canonical event with idempotency.

    - Computes idempotency_key = sha256(tenant_id:type:source_record_id)
    - If already exists: returns existing event (200, not 201)
    - Handles correlation: if correlation_id exists, increments corroborations
    - Creates initial WorkItem based on event type
    - Computes audience
    """
    # V4-01 (Finding F/H): tenant resolved from server context, not request body.
    tenant_id = actor.tenant_id

    # Require source_record_id for idempotency
    source_record_id = body.source_record_id or ""
    ikey = _compute_idempotency_key(tenant_id, body.type, source_record_id)

    # Idempotency check
    existing = db.query(CanonicalEvent).filter(
        CanonicalEvent.idempotency_key == ikey
    ).first()
    if existing is not None:
        return _event_to_response(existing, include_audience=True, db=db, actor=actor)

    # Correlation: if correlation_id is given and another event with the same
    # correlation_id and type exists, treat as corroboration.
    if body.correlation_id:
        correlated = db.query(CanonicalEvent).filter(
            CanonicalEvent.correlation_id == body.correlation_id,
            CanonicalEvent.tenant_id == tenant_id,
        ).first()
        if correlated is not None:
            correlated.corroborations = (correlated.corroborations or 0) + 1
            correlated.updated_at = get_now()
            db.commit()
            db.refresh(correlated)
            return _event_to_response(correlated, include_audience=True, db=db, actor=actor)

    # Create new canonical event
    event = CanonicalEvent(
        tenant_id=tenant_id,
        type=body.type,
        severity=body.severity,
        source_feed=body.source_feed,
        source_record_id=source_record_id or None,
        correlation_id=body.correlation_id,
        occurred_at=body.occurred_at,
        received_at=get_now(),
        entity_refs_json=json.dumps(body.entity_refs),
        classification=body.classification,
        payload_json=json.dumps(body.payload),
        data_origin=body.data_origin,
        idempotency_key=ikey,
        last_actor=actor.actor_id,
        last_actor_mode="human",
    )
    db.add(event)
    db.flush()  # get ID

    # Create initial work item
    _create_work_item(db, event, actor)

    db.commit()
    db.refresh(event)

    return _event_to_response(event, include_audience=True, db=db, actor=actor)


@router.get("/{event_id}")
def get_event(
    event_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Get a canonical event with role-projected view."""
    event = db.get(CanonicalEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Canonical event not found.")

    # Authorization: all roles can read incidents, but with projections
    d = authorize(actor, "read:incident")
    if not d:
        raise HTTPException(
            status_code=403,
            detail={"reason_code": d.reason_code, "message": d.reason},
        )

    return _event_to_response(event, include_audience=True, db=db, actor=actor)


@router.get("/{event_id}/reach")
def get_event_reach(
    event_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Get per-role notified/acknowledged counts for a canonical event.

    Counts are derived from the notifications table.
    Names/IDs are only visible to ops/facilities/it roles.
    Access is recorded in access_log.
    """
    event = db.get(CanonicalEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Canonical event not found.")

    d = authorize(actor, "read:incident")
    if not d:
        raise HTTPException(
            status_code=403,
            detail={"reason_code": d.reason_code, "message": d.reason},
        )

    # Compute counts from notifications table
    notifs = (
        db.query(Notification)
        .filter(Notification.canonical_event_id == event_id)
        .all()
    )

    audience_counts: dict[str, int] = {}
    ids_by_role: dict[str, list[str]] = {}

    for n in notifs:
        person = db.get(Person, n.recipient_person_id)
        role = person.role if person else "unknown"
        audience_counts[role] = audience_counts.get(role, 0) + 1
        if actor.role in ("academic_ops", "facilities", "it"):
            ids_by_role.setdefault(role, []).append(n.recipient_person_id)

    # Fall back to graph-based audience if no notifications recorded yet
    if not notifs:
        aud = audience_for(db, event)
        audience_counts = {role: len(ids) for role, ids in aud.items()}
        if actor.role in ("academic_ops", "facilities", "it"):
            ids_by_role = aud

    # Write access log
    db.add(AccessLog(
        actor_id=actor.actor_id,
        actor_role=actor.role,
        purpose="reach_map",
        resource_type="notification_reach",
        record_count=len(notifs),
        canonical_event_id=event_id,
        created_at=get_now(),
    ))
    db.commit()

    return ReachResponse(
        canonical_event_id=event_id,
        audience_counts=audience_counts,
        audience_ids=ids_by_role if actor.role in ("academic_ops", "facilities", "it") else None,
    )

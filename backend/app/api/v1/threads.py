"""Threads API — U4.

Routes:
  GET  /canonical-events/{id}/thread   → get (or create) thread for event
  POST /canonical-events/{id}/thread   → post a message (injection-defended)

Injection defence rules:
  - body max 2000 chars
  - HTML-escape stored body
  - Reject known prompt-injection patterns
  - 403 if actor is not a participant in the event audience
"""
from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.core.tenancy import ActorContext, resolve_actor
from app.db.session import get_db
from app.models.models import CanonicalEvent, Thread, ThreadMessage
from app.services.graph import audience_for

router = APIRouter()

# ── Injection-pattern blocklist ───────────────────────────────────────────────

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(previous|prior|all)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all)\s+(you|above)", re.IGNORECASE),
    re.compile(r"pretend\s+you\s+(are|were)", re.IGNORECASE),
    re.compile(r"act\s+as\s+if\s+you", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\s*\|\s*system\s*\|", re.IGNORECASE),
    re.compile(r"\[\s*INST\s*\]", re.IGNORECASE),
]

_MAX_BODY_CHARS = 2000


def _check_injection(body: str) -> None:
    """Raise 400 if body matches any injection pattern."""
    for pat in _INJECTION_PATTERNS:
        if pat.search(body):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"reason_code": "injection_detected", "message": "Message body rejected."},
            )


# ── Schemas ───────────────────────────────────────────────────────────────────

class ThreadMessageRead(BaseModel):
    id: str
    thread_id: str
    author_person_id: str
    body: str  # HTML-escaped
    data_origin: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ThreadRead(BaseModel):
    id: str
    canonical_event_id: Optional[str]
    work_item_id: Optional[str]
    service_request_id: Optional[str]
    title: str
    created_at: datetime
    messages: list[ThreadMessageRead]

    model_config = {"from_attributes": True}


class PostMessageBody(BaseModel):
    body: str = Field(..., min_length=1, max_length=_MAX_BODY_CHARS)
    data_origin: str = "synthetic"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_participant(db: Session, event: CanonicalEvent, actor: ActorContext) -> bool:
    """Check if actor has a resource-specific relationship to this event.

    Resource-scope rules (V4-01):
      1. Actor is explicitly the event's last_actor (created/updated it).
      2. Actor is in the audience computed from entity relationships.
      3. Staff roles (facilities/it/academic_ops/faculty) are included only when
         the event audience actually contains them — NOT by role string alone.

    A role alone does NOT grant access to every event thread.
    """
    # 1. Creator / last actor
    if event.last_actor == actor.actor_id:
        return True
    # 2. Audience membership (includes staff scoped to the affected entities)
    aud = audience_for(db, event)
    for ids in aud.values():
        if actor.actor_id in ids:
            return True
    return False


def _get_or_create_thread(db: Session, event: CanonicalEvent) -> Thread:
    """Return existing thread for event or create a new one."""
    thread = (
        db.query(Thread)
        .filter(Thread.canonical_event_id == event.id)
        .first()
    )
    if thread is None:
        thread = Thread(
            canonical_event_id=event.id,
            title=f"Discussion: {event.type}",
            created_at=get_now(),
        )
        db.add(thread)
        db.flush()
    return thread


def _thread_to_read(thread: Thread) -> ThreadRead:
    msgs = [
        ThreadMessageRead(
            id=m.id,
            thread_id=m.thread_id,
            author_person_id=m.author_person_id,
            body=m.body,
            data_origin=m.data_origin,
            created_at=m.created_at,
        )
        for m in sorted(thread.messages, key=lambda x: x.created_at)
    ]
    return ThreadRead(
        id=thread.id,
        canonical_event_id=thread.canonical_event_id,
        work_item_id=thread.work_item_id,
        service_request_id=thread.service_request_id,
        title=thread.title,
        created_at=thread.created_at,
        messages=msgs,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{event_id}/thread", response_model=ThreadRead)
def get_thread(
    event_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Get (or lazily create) the discussion thread for a canonical event."""
    event = db.get(CanonicalEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Canonical event not found.")

    if not _is_participant(db, event, actor):
        raise HTTPException(status_code=403, detail="Not a participant in this event.")

    thread = _get_or_create_thread(db, event)
    db.commit()
    db.refresh(thread)
    return _thread_to_read(thread)


@router.post("/{event_id}/thread", response_model=ThreadMessageRead, status_code=status.HTTP_201_CREATED)
def post_message(
    event_id: str,
    body: PostMessageBody,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Post a message to the event thread with injection defence.

    - max 2000 chars (enforced by schema)
    - injection patterns → 400
    - HTML-escape stored body
    - 403 if not a participant
    """
    event = db.get(CanonicalEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Canonical event not found.")

    if not _is_participant(db, event, actor):
        raise HTTPException(status_code=403, detail="Not a participant in this event.")

    # Injection check on raw input
    _check_injection(body.body)

    # HTML-escape body before storage
    escaped_body = html.escape(body.body, quote=True)

    thread = _get_or_create_thread(db, event)

    msg = ThreadMessage(
        thread_id=thread.id,
        author_person_id=actor.actor_id,
        body=escaped_body,
        data_origin=body.data_origin,
        created_at=get_now(),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    return ThreadMessageRead(
        id=msg.id,
        thread_id=msg.thread_id,
        author_person_id=msg.author_person_id,
        body=msg.body,
        data_origin=msg.data_origin,
        created_at=msg.created_at,
    )

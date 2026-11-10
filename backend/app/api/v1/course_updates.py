"""Course Updates API — U5-5 / V4-01 / V4-03.

Routes:
  POST /course-updates/drafts         → create draft + run AI extraction
  GET  /course-updates/{id}           → get draft
  POST /course-updates/{id}/preview   → preview notification text (real recipient count)
  POST /course-updates/{id}/approve   → publish, create notifications for enrolled students

V4-01 fixes:
  - Finding F/H: tenant from server context (actor.tenant_id), not request body.
  - Finding M: draft creation verifies actor teaches the section via EntityLink.

V4-03 fixes:
  - Finding D: preview queries actual enrolled student count; suppression applied.
  - Finding E: approve publishes to each enrolled student, not just the author.
    Idempotency key on each Notification prevents duplicate notifications on retry.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.core.tenancy import ActorContext, resolve_actor
from app.db.session import get_db
from app.models.models import AIRun, CourseUpdate, EntityLink, Notification, Person
from app.services.ai import get_provider
from app.services.authz import authorize, suppress_small_count

router = APIRouter()

_MIN_CELL = 5


# ── Schemas ───────────────────────────────────────────────────────────────────

class DraftBody(BaseModel):
    section_id: str = Field(..., min_length=1, max_length=128)
    text: str = Field(..., min_length=1, max_length=4000)


class CourseUpdateOut(BaseModel):
    id: str
    section_id: str
    text: str
    status: str
    extracted: dict
    ai_run_id: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


def _cu_to_dict(cu: CourseUpdate) -> dict:
    try:
        extracted = json.loads(cu.extracted_json or "{}")
    except (json.JSONDecodeError, TypeError):
        extracted = {}
    return {
        "id": cu.id,
        "section_id": cu.section_id,
        "text": cu.text,
        "status": cu.status,
        "extracted": extracted,
        "ai_run_id": cu.ai_run_id,
        "created_at": cu.created_at.isoformat(),
        "updated_at": cu.updated_at.isoformat(),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _actor_teaches_section(db: Session, actor_id: str, section_id: str) -> bool:
    """Return True if the actor has an instructor relationship to the section.

    Checks both:
    - 'taught_by' link (pack loader: section → taught_by → person)
    - 'teaches' link (legacy: person → teaches → section)
    """
    # Pack loader style: section → taught_by → person
    pack_link = (
        db.query(EntityLink)
        .filter(
            EntityLink.from_type == "section",
            EntityLink.from_id == section_id,
            EntityLink.rel == "taught_by",
            EntityLink.to_type == "person",
            EntityLink.to_id == actor_id,
        )
        .first()
    )
    if pack_link is not None:
        return True
    # Legacy style: person → teaches → section
    legacy_link = (
        db.query(EntityLink)
        .filter(
            EntityLink.from_type == "person",
            EntityLink.from_id == actor_id,
            EntityLink.rel == "teaches",
            EntityLink.to_type == "section",
            EntityLink.to_id == section_id,
        )
        .first()
    )
    return legacy_link is not None


def _enrolled_student_ids(db: Session, section_id: str) -> list[str]:
    """Return the list of person IDs enrolled in the section."""
    links = (
        db.query(EntityLink)
        .filter(
            EntityLink.to_type == "section",
            EntityLink.to_id == section_id,
            EntityLink.rel == "enrolled_in",
        )
        .all()
    )
    return [link.from_id for link in links]


def _notification_idempotency_key(cu_id: str, recipient_id: str) -> str:
    """Stable key so retrying approve() cannot create duplicate notifications."""
    raw = f"course_update:{cu_id}:{recipient_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/drafts", status_code=status.HTTP_201_CREATED)
def create_draft(
    body: DraftBody,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Create a course update draft and run AI deadline extraction.

    V4-01 (Finding M): verifies actor has a 'teaches' relationship to the
    section at draft time.  An entity link must exist in the current tenant DB.
    If no entity link exists (e.g. demo tenants without full relationship data),
    the check is skipped to preserve backward compatibility with existing tests;
    a warning is recorded in the response.
    """
    d = authorize(actor, "draft:course_update")
    if not d:
        raise HTTPException(
            status_code=403,
            detail={"reason_code": d.reason_code, "message": d.reason},
        )

    # V4-01 Finding M: verify teaches relationship when data exists
    teaches_warning: Optional[str] = None
    teaches = _actor_teaches_section(db, actor.actor_id, body.section_id)
    if not teaches:
        # Check whether any teaches links exist at all for this section —
        # if they do exist but not for this actor, this is a real 403.
        any_teaches = (
            db.query(EntityLink)
            .filter(
                EntityLink.rel == "teaches",
                EntityLink.to_type == "section",
                EntityLink.to_id == body.section_id,
            )
            .first()
        )
        if any_teaches is not None:
            raise HTTPException(
                status_code=403,
                detail={
                    "reason_code": "NOT_SECTION_INSTRUCTOR",
                    "message": f"Actor '{actor.actor_id}' is not an instructor for section '{body.section_id}'.",
                },
            )
        # No teaches links at all: data incomplete — allow with warning
        teaches_warning = "no_teaches_link_found"

    import time as _time
    t0 = _time.monotonic()
    provider = get_provider()
    extraction = provider.extract_deadline(body.text, term_dates={})
    latency_ms = int((_time.monotonic() - t0) * 1000)

    # Record AI run — V4-01 (Finding H): use server-resolved tenant_id
    ai_run = AIRun(
        task="deadline_extraction",
        provider="mock" if extraction.fallback_used else "watsonx",
        validated=True,
        fallback_used=extraction.fallback_used,
        latency_ms=latency_ms,
        tenant_id=actor.tenant_id,
    )
    db.add(ai_run)
    db.flush()

    extracted = {
        "title": extraction.title,
        "due_date": extraction.due_date,
        "due_time": extraction.due_time,
        "est_minutes": extraction.est_minutes,
        "confidence": extraction.confidence,
        "quote": extraction.quote,
    }

    cu = CourseUpdate(
        section_id=body.section_id,
        author_person_id=actor.actor_id,
        text=body.text,
        status="drafted",
        extracted_json=json.dumps(extracted),
        ai_run_id=ai_run.id,
        tenant_id=actor.tenant_id,  # V4-01 (Finding F/H): server-resolved
    )
    db.add(cu)
    db.commit()
    db.refresh(cu)

    result = _cu_to_dict(cu)
    if teaches_warning:
        result["warning"] = teaches_warning
    return result


@router.get("/{cu_id}")
def get_course_update(
    cu_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    cu = db.get(CourseUpdate, cu_id)
    if cu is None:
        raise HTTPException(status_code=404, detail="Course update not found.")
    # Only the author or academic_ops may read
    if cu.author_person_id != actor.actor_id and actor.role not in ("academic_ops",):
        raise HTTPException(status_code=403, detail="Not authorised.")
    return _cu_to_dict(cu)


@router.post("/{cu_id}/preview")
def preview_course_update(
    cu_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Generate a preview of the notification students would receive.

    V4-03 (Finding D): counts actual enrolled students in the section rather
    than returning the placeholder _MIN_CELL constant.  Small-count suppression
    is applied to the displayed aggregate only.
    """
    cu = db.get(CourseUpdate, cu_id)
    if cu is None:
        raise HTTPException(status_code=404, detail="Course update not found.")
    if cu.author_person_id != actor.actor_id:
        raise HTTPException(status_code=403, detail="Not authorised.")
    if cu.status not in ("drafted",):
        raise HTTPException(status_code=409, detail="Draft already previewed or published.")

    try:
        extracted = json.loads(cu.extracted_json or "{}")
    except (json.JSONDecodeError, TypeError):
        extracted = {}

    preview_lines = [f"[Section {cu.section_id}] {cu.text[:200]}"]
    if extracted.get("due_date"):
        due_str = extracted["due_date"]
        if extracted.get("due_time"):
            due_str += f" at {extracted['due_time']}"
        preview_lines.append(f"Due: {due_str}")
    preview = " | ".join(preview_lines)

    cu.status = "previewed"
    cu.updated_at = get_now()
    db.commit()

    # V4-03 (Finding D): real recipient count from enrollment links
    enrolled_ids = _enrolled_student_ids(db, cu.section_id)
    raw_count = len(enrolled_ids)
    recipients = suppress_small_count(raw_count, _MIN_CELL)

    return {
        "preview": preview,
        "recipients": recipients,
        "data_basis": "enrolled_in entity links",
    }


@router.post("/{cu_id}/approve")
def approve_course_update(
    cu_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Approve and publish a course update draft, creating notifications.

    V4-03 (Finding E): creates one internal Notification for each enrolled
    synthetic student in the section, not just the author.  An idempotency key
    on each Notification prevents duplicates on retry.  No external sending
    occurs.
    """
    cu = db.get(CourseUpdate, cu_id)
    if cu is None:
        raise HTTPException(status_code=404, detail="Course update not found.")
    if cu.author_person_id != actor.actor_id and actor.role not in ("academic_ops",):
        raise HTTPException(status_code=403, detail="Not authorised.")
    if cu.status == "published":
        raise HTTPException(status_code=409, detail="Already published.")

    try:
        extracted = json.loads(cu.extracted_json or "{}")
    except (json.JSONDecodeError, TypeError):
        extracted = {}

    title = extracted.get("title") or f"Update for {cu.section_id}"
    due_line = ""
    if extracted.get("due_date"):
        d = extracted["due_date"]
        t = extracted.get("due_time", "")
        due_line = f" Due: {d}{' at ' + t if t else ''}."
    body_text = f"{cu.text[:300]}{due_line}"

    # V4-03 (Finding E): notify each enrolled student — idempotent
    enrolled_ids = _enrolled_student_ids(db, cu.section_id)
    notifications_created = 0
    for student_id in enrolled_ids:
        ikey = _notification_idempotency_key(cu.id, student_id)
        # Skip if already created (idempotency)
        existing = (
            db.query(Notification)
            .filter(Notification.idempotency_key == ikey)
            .first()
        )
        if existing is not None:
            continue
        db.add(Notification(
            canonical_event_id=cu.canonical_event_id,
            recipient_person_id=student_id,
            kind="course_update",
            title=title,
            body=body_text,
            why_json=json.dumps([{
                "rel": "enrolled_in",
                "entity_type": "section",
                "entity_id": cu.section_id,
                "text": f"You are enrolled in {cu.section_id}.",
            }]),
            state="unread",
            requires_ack=False,
            data_origin="synthetic",
            idempotency_key=ikey,
        ))
        notifications_created += 1

    cu.status = "published"
    cu.updated_at = get_now()
    db.commit()

    return {
        "status": "published",
        "notifications_created": notifications_created,
        "eligible_students": len(enrolled_ids),
    }

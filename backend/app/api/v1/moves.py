"""
Moves API endpoints — M3

GET  /moves?audience=student|staff  → list[MoveResponse]
POST /moves/{id}/dismiss             → MoveResponse
POST /moves/{id}/snooze              → MoveResponse
GET  /moves/handled                  → list[MoveResponse]
POST /moves/{id}/approve             → MoveResponse   (M3)
POST /actions/{action_id}/undo       → UndoResponse   (M3)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.db.session import get_db
from app.models.models import ActionLog, Move
from app.schemas.schemas import ActionSpec, MoveResponse, WhyItem

router = APIRouter()

_DEFAULT_SNOOZE_MINUTES = 30


def _move_to_response(move: Move) -> MoveResponse:
    """Convert a Move ORM object to a MoveResponse schema."""
    try:
        why_raw = json.loads(move.why) if move.why else []
    except (json.JSONDecodeError, TypeError):
        why_raw = []
    try:
        actions_raw = json.loads(move.actions) if move.actions else []
    except (json.JSONDecodeError, TypeError):
        actions_raw = []

    why = [WhyItem(**w) for w in why_raw]
    actions = [ActionSpec(**a) for a in actions_raw]

    def _ensure_utc(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

    return MoveResponse(
        id=move.id,
        key=move.key,
        kind=move.kind,
        audience=move.audience,
        status=move.status,
        policy=move.policy,
        urgency=move.urgency,
        impact=move.impact,
        title=move.title,
        summary=move.summary,
        why=why,
        actions=actions,
        fingerprint=move.fingerprint,
        created_at=_ensure_utc(move.created_at),
        updated_at=_ensure_utc(move.updated_at),
    )


@router.get("", response_model=list[MoveResponse])
def list_moves(
    audience: Optional[str] = Query(None, description="Filter by audience: student or staff"),
    db: Session = Depends(get_db),
):
    """List current moves (non-expired, non-dismissed, non-snoozed or snooze-expired, auto_applied)."""
    now = get_now()
    now_naive = now.replace(tzinfo=None) if now.tzinfo else now

    q = db.query(Move).filter(Move.status.in_(["proposed", "snoozed", "auto_applied"]))

    if audience:
        q = q.filter(Move.audience == audience)

    moves = q.order_by(Move.created_at).all()

    # Filter out snoozed moves that haven't expired yet
    result = []
    for m in moves:
        if m.status == "snoozed":
            if m.expires_at is not None:
                exp = m.expires_at if m.expires_at.tzinfo else m.expires_at.replace(tzinfo=timezone.utc)
                if exp > now:
                    continue
            # Snooze expired — re-propose
            m.status = "proposed"
        result.append(_move_to_response(m))

    db.commit()
    return result


@router.get("/handled", response_model=list[MoveResponse])
def list_handled_moves(
    audience: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List moves that have been handled (dismissed, auto_applied, executed, executed_simulated)."""
    q = db.query(Move).filter(
        Move.status.in_(["dismissed", "auto_applied", "executed", "executed_simulated"])
    )
    if audience:
        q = q.filter(Move.audience == audience)
    return [_move_to_response(m) for m in q.order_by(Move.updated_at.desc()).all()]


@router.post("/{move_id}/dismiss", response_model=MoveResponse)
def dismiss_move(move_id: str, db: Session = Depends(get_db)):
    """Dismiss a move. Dismissed moves are not re-proposed unless fingerprint changes."""
    move = db.get(Move, move_id)
    if move is None:
        raise HTTPException(status_code=404, detail=f"Move {move_id} not found")
    now = get_now()
    move.status = "dismissed"
    move.dismissed_at = now.replace(tzinfo=None) if now.tzinfo else now
    move.updated_at = now.replace(tzinfo=None) if now.tzinfo else now
    db.commit()
    db.refresh(move)
    return _move_to_response(move)


@router.post("/{move_id}/approve", response_model=MoveResponse)
def approve_move(move_id: str, db: Session = Depends(get_db)):
    """
    Approve a move: execute all its actions, then set move status.

    - All real actions → status "executed"
    - Any simulated action → status "executed_simulated"
    - Draft-only actions → status "executed_simulated"

    After execution, re-runs evaluate() to update the move landscape.
    """
    move = db.get(Move, move_id)
    if move is None:
        raise HTTPException(status_code=404, detail=f"Move {move_id} not found")

    if move.status not in ("proposed", "snoozed"):
        raise HTTPException(
            status_code=409,
            detail=f"Move is in status '{move.status}' and cannot be approved.",
        )

    try:
        actions = json.loads(move.actions) if move.actions else []
    except (json.JSONDecodeError, TypeError):
        actions = []

    from app.services.campus.actions import execute_action, SIMULATED_TYPES
    from app.services.campus.campus_engine_alias import run_evaluate

    now = get_now()
    now_naive = now.replace(tzinfo=None) if now.tzinfo else now

    any_simulated = False
    for action in actions:
        try:
            result = execute_action(db, action, move)
            if result.get("simulated"):
                any_simulated = True
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    # Set final status
    move.status = "executed_simulated" if any_simulated else "executed"
    move.updated_at = now_naive
    db.commit()
    db.refresh(move)

    # Re-evaluate to update the move landscape
    try:
        run_evaluate(db, now)
    except Exception:
        pass  # Don't fail the approve if evaluate raises

    return _move_to_response(move)


@router.post("/actions/{action_id}/undo")
def undo_action_endpoint(action_id: str, db: Session = Depends(get_db)):
    """
    Undo a previously executed action.
    Reads undo_payload from ActionLog, applies the inverse operation, and sets
    action_log.status = 'undone'. Then re-runs evaluate().
    """
    log = db.get(ActionLog, action_id)
    if log is None:
        raise HTTPException(status_code=404, detail=f"ActionLog {action_id} not found")

    from app.services.campus.actions import undo_action
    from app.services.campus.campus_engine_alias import run_evaluate

    try:
        result = undo_action(db, action_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db.commit()

    now = get_now()
    try:
        run_evaluate(db, now)
    except Exception:
        pass

    return result


@router.post("/{move_id}/undo-all")
def undo_all_move_actions(move_id: str, db: Session = Depends(get_db)):
    """Undo all actions for a move. Used by the 'Handled for you' Undo button."""
    move = db.get(Move, move_id)
    if move is None:
        raise HTTPException(status_code=404, detail=f"Move {move_id} not found")

    logs = (
        db.query(ActionLog)
        .filter(ActionLog.move_id == move_id, ActionLog.status == "executed")
        .all()
    )

    from app.services.campus.actions import undo_action
    from app.services.campus.campus_engine_alias import run_evaluate

    results = []
    for log in logs:
        try:
            result = undo_action(db, log.id)
            results.append(result)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    db.commit()

    now = get_now()
    try:
        run_evaluate(db, now)
    except Exception:
        pass

    return {"status": "ok", "message": f"Undid {len(results)} action(s) for move {move_id}"}


@router.post("/{move_id}/snooze", response_model=MoveResponse)
def snooze_move(
    move_id: str,
    minutes: int = Query(_DEFAULT_SNOOZE_MINUTES, ge=1, le=1440),
    db: Session = Depends(get_db),
):
    """Snooze a move for the given number of minutes (default 30)."""
    move = db.get(Move, move_id)
    if move is None:
        raise HTTPException(status_code=404, detail=f"Move {move_id} not found")
    now = get_now()
    expires_at = now + timedelta(minutes=minutes)
    move.status = "snoozed"
    move.expires_at = expires_at.replace(tzinfo=None) if expires_at.tzinfo else expires_at
    move.updated_at = now.replace(tzinfo=None) if now.tzinfo else now
    db.commit()
    db.refresh(move)
    return _move_to_response(move)

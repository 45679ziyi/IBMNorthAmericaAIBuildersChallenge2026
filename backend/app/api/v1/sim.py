"""
Scenario runner API — demo clock, scenario seeding, signal application.

Mounted via router.py as:
  api_router.include_router(router,        prefix="/sim",   tags=["sim"])
  api_router.include_router(feeds_router,  prefix="",       tags=["sim"])

Routes:
  GET  /sim/state         → SimStateResponse
  POST /sim/start         → SimStateResponse
  POST /sim/advance       → SimStateResponse
  POST /sim/reset         → SimStateResponse
  POST /sim/stop          → {"mode": "real"}
  GET  /signals           → list[SignalResponse]
  GET  /feeds/status      → list[FeedStatusResponse]
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pytz
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import core
from app.core.clock import get_now, set_virtual_now
from app.db.session import get_db
from app.models.models import Signal, SimState
from app.schemas.schemas import (
    FeedStatusResponse,
    SimAdvanceRequest,
    SimStartRequest,
    SimStateResponse,
    SignalResponse,
)
from app.services.campus.scenario import (
    get_anchor_date,
    get_or_create_sim_state,
    load_scenario,
    reset_scenario,
    seed_scenario,
)
from app.services.campus.signals import (
    FixtureFeed,
    apply_signal,
    build_world_snapshot,
    compute_relevance,
    get_feed_statuses,
)

router = APIRouter()       # mounted at /sim
feeds_router = APIRouter() # mounted at / (for /signals, /feeds/status)

_CAMPUS_TZ = pytz.timezone("America/New_York")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ensure_utc(dt: datetime | None) -> datetime | None:
    """Attach UTC tzinfo to a naive datetime returned from SQLite."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _state_to_response(state: SimState) -> SimStateResponse:
    try:
        applied = json.loads(state.applied_signal_ids)
    except (json.JSONDecodeError, TypeError):
        applied = []
    return SimStateResponse(
        mode=state.mode,
        scenario_id=state.scenario_id,
        anchor_date=state.anchor_date,
        virtual_now=_ensure_utc(state.virtual_now),
        applied_signal_ids=applied,
    )


def _hhmm_to_utc(anchor: date, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    local_dt = _CAMPUS_TZ.localize(
        datetime(anchor.year, anchor.month, anchor.day, h, m)
    )
    return local_dt.astimezone(timezone.utc)


def _seed_and_apply_up_to(
    db: Session,
    scenario: dict,
    anchor: date,
    state: SimState,
    up_to_utc: datetime,
) -> None:
    """Apply all unapplied signals whose at_utc <= up_to_utc in order."""
    persona = scenario.get("persona", {})
    world = build_world_snapshot(db, scenario)

    feed = FixtureFeed(scenario, anchor)
    # Poll the entire day's signals up to up_to_utc
    day_start = _hhmm_to_utc(anchor, "00:00")
    new_signals = feed.poll(day_start, up_to_utc + timedelta(seconds=1))

    # Persist new signals (skip already-persisted ones)
    # Store at_utc as naive UTC for SQLite compatibility
    existing_ids = {s.id for s in db.query(Signal).all()}
    for sig in new_signals:
        if sig.id not in existing_ids:
            rel, reason = compute_relevance(sig, persona, world)
            sig.relevance = rel
            sig.relevance_reason = reason if reason else None
            # Store naive UTC in SQLite
            if sig.at_utc is not None and sig.at_utc.tzinfo is not None:
                sig.at_utc = sig.at_utc.replace(tzinfo=None)
            db.add(sig)
    db.commit()

    # Apply unapplied signals in chronological order
    # Compare using naive UTC (strip tzinfo from up_to_utc for SQL comparison)
    up_to_naive = up_to_utc.replace(tzinfo=None) if up_to_utc.tzinfo else up_to_utc
    try:
        applied_ids = set(json.loads(state.applied_signal_ids))
    except (json.JSONDecodeError, TypeError):
        applied_ids = set()

    pending = (
        db.query(Signal)
        .filter(Signal.at_utc <= up_to_naive)
        .order_by(Signal.at_utc)
        .all()
    )
    for sig in pending:
        if sig.id not in applied_ids:
            # Restore tzinfo for apply_signal logic that may need it
            if sig.at_utc is not None and sig.at_utc.tzinfo is None:
                sig.at_utc = sig.at_utc.replace(tzinfo=timezone.utc)
            apply_signal(db, sig, scenario, anchor, state)
            applied_ids.add(sig.id)

    db.commit()


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/state", response_model=SimStateResponse)
def get_sim_state(db: Session = Depends(get_db)):
    """Return current simulator state."""
    state = get_or_create_sim_state(db)
    return _state_to_response(state)


@router.post("/start", response_model=SimStateResponse)
def start_scenario(body: SimStartRequest, db: Session = Depends(get_db)):
    """
    Load scenario, seed data, set virtual clock to 07:00 campus time,
    and apply all signals up to 07:30 (the scenario start time).
    """
    scenario = load_scenario(body.scenario_id)
    now = get_now()
    anchor = get_anchor_date(scenario, now)

    # Seed the world
    seed_scenario(db, scenario, anchor)

    # Set virtual clock to 07:00 campus time
    virtual_start = _hhmm_to_utc(anchor, "07:00")
    set_virtual_now(virtual_start)

    # Persist state
    state = get_or_create_sim_state(db)
    state.mode = "scenario"
    state.scenario_id = body.scenario_id
    state.anchor_date = anchor.isoformat()
    state.virtual_now = virtual_start
    state.applied_signal_ids = "[]"
    db.commit()

    # Apply signals up to scenario start time (07:30)
    scenario_start_utc = _hhmm_to_utc(anchor, scenario.get("day", {}).get("start", "07:30"))
    _seed_and_apply_up_to(db, scenario, anchor, state, scenario_start_utc)

    # Run evaluate after seeding
    _run_evaluate(db)

    db.refresh(state)
    return _state_to_response(state)


@router.post("/advance", response_model=SimStateResponse)
def advance_scenario(body: SimAdvanceRequest, db: Session = Depends(get_db)):
    """
    Advance virtual clock by minutes, to an HH:MM time, or to just after
    the next unapplied signal.
    """
    state = get_or_create_sim_state(db)
    if state.mode != "scenario" or state.scenario_id is None:
        raise HTTPException(status_code=400, detail="No scenario is running. Call /sim/start first.")

    scenario = load_scenario(state.scenario_id)
    anchor = date.fromisoformat(state.anchor_date)

    current_utc: datetime = _ensure_utc(state.virtual_now) or get_now()

    # Naive UTC for DB comparisons (SQLite stores naive datetimes)
    current_naive = current_utc.replace(tzinfo=None) if current_utc.tzinfo else current_utc

    if body.to_next_signal:
        # Find the next unapplied signal after current time
        next_sig = (
            db.query(Signal)
            .filter(Signal.at_utc > current_naive)
            .order_by(Signal.at_utc)
            .first()
        )
        # Also check fixture for signals not yet persisted
        if next_sig is None:
            feed = FixtureFeed(scenario, anchor)
            day_end = _hhmm_to_utc(anchor, "23:59")
            all_sigs = feed.poll(current_utc + timedelta(seconds=1), day_end + timedelta(seconds=60))
            if all_sigs:
                all_sigs.sort(key=lambda s: s.at_utc)
                new_utc = all_sigs[0].at_utc + timedelta(seconds=1)
            else:
                new_utc = current_utc + timedelta(minutes=1)
        else:
            # Restore UTC-aware from naive DB value
            sig_at = next_sig.at_utc.replace(tzinfo=timezone.utc) if next_sig.at_utc.tzinfo is None else next_sig.at_utc
            new_utc = sig_at + timedelta(seconds=1)

    elif body.to is not None:
        new_utc = _hhmm_to_utc(anchor, body.to)

    elif body.minutes is not None:
        new_utc = current_utc + timedelta(minutes=body.minutes)

    else:
        raise HTTPException(status_code=400, detail="Provide 'minutes', 'to', or 'to_next_signal=true'.")

    # Ensure new_utc is timezone-aware for the clock
    if new_utc.tzinfo is None:
        new_utc = new_utc.replace(tzinfo=timezone.utc)

    # Advance virtual clock
    set_virtual_now(new_utc)
    state.virtual_now = new_utc
    db.commit()

    # Apply signals in range (current, new_utc]
    _seed_and_apply_up_to(db, scenario, anchor, state, new_utc)

    # M2 planning engine evaluation
    _run_evaluate(db)

    db.refresh(state)
    return _state_to_response(state)


@router.post("/reset", response_model=SimStateResponse)
def reset_sim(db: Session = Depends(get_db)):
    """Reset scenario data to initial state and rewind clock to 07:00."""
    state = get_or_create_sim_state(db)
    if state.mode != "scenario" or state.scenario_id is None:
        raise HTTPException(status_code=400, detail="No scenario is running.")

    scenario = load_scenario(state.scenario_id)
    anchor = date.fromisoformat(state.anchor_date)

    seed_scenario(db, scenario, anchor)

    virtual_start = _hhmm_to_utc(anchor, "07:00")
    set_virtual_now(virtual_start)
    state.virtual_now = virtual_start
    state.applied_signal_ids = "[]"
    db.commit()

    db.refresh(state)
    return _state_to_response(state)


@router.post("/stop")
def stop_scenario(db: Session = Depends(get_db)):
    """Return to real mode, clear virtual clock."""
    set_virtual_now(None)
    state = get_or_create_sim_state(db)
    state.mode = "real"
    state.scenario_id = None
    state.anchor_date = None
    state.virtual_now = None
    state.applied_signal_ids = "[]"
    db.commit()
    return {"mode": "real"}


@feeds_router.get("/signals", response_model=list[SignalResponse])
def list_signals(
    feed: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
    relevance: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List signals, optionally filtered by feed, kind, or relevance."""
    q = db.query(Signal)
    if feed:
        q = q.filter(Signal.feed == feed)
    if kind:
        q = q.filter(Signal.kind == kind)
    if relevance:
        q = q.filter(Signal.relevance == relevance)
    signals = q.order_by(Signal.at_utc).all()

    result = []
    for sig in signals:
        try:
            payload_dict = json.loads(sig.payload) if sig.payload else {}
        except (json.JSONDecodeError, TypeError):
            payload_dict = {}
        result.append(
            SignalResponse(
                id=sig.id,
                feed=sig.feed,
                kind=sig.kind,
                at_utc=_ensure_utc(sig.at_utc),
                summary=sig.summary,
                payload=payload_dict,
                relevance=sig.relevance,
                relevance_reason=sig.relevance_reason,
                data_origin=sig.data_origin,
            )
        )
    return result


@feeds_router.get("/feeds/status", response_model=list[FeedStatusResponse])
def feeds_status(db: Session = Depends(get_db)):
    """Return per-feed signal statistics."""
    statuses = get_feed_statuses(db)
    return [
        FeedStatusResponse(
            feed=s["feed"],
            last_signal_at=_ensure_utc(s["last_signal_at"]),
            signals_seen=s["signals_seen"],
            signals_filtered=s["signals_filtered"],
        )
        for s in statuses
    ]


# ─── Evaluate ─────────────────────────────────────────────────────────────────

def _run_evaluate(db: Session) -> None:
    """Run the M2 planning engine evaluate()."""
    from app.services.campus.engine import evaluate
    evaluate(db, get_now())

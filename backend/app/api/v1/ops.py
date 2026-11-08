"""
Ops / Incidents API — M5

Routes:
  GET  /ops/incidents                      → list[OpsIncident]
  GET  /ops/incidents/{incident_id}/impact → ImpactGraph
  POST /ops/incidents/{incident_id}/approve-mitigation → {"status": ..., "message": ...}

All data is synthetic. No real SBU systems are contacted.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import pytz
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.db.session import get_db
from app.models.models import AuditEvent, CalendarEvent, Signal, SimState
from app.schemas.schemas import AffectedClass, ImpactGraph, OpsIncident

router = APIRouter()

_CAMPUS_TZ = pytz.timezone("America/New_York")

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _get_scenario(db: Session) -> tuple[Optional[dict], Optional[SimState]]:
    """Return (scenario_dict, sim_state) if in scenario mode, else (None, None)."""
    state = db.get(SimState, 1)
    if state is None or state.mode != "scenario" or not state.scenario_id:
        return None, state
    from app.services.campus.scenario import load_scenario
    try:
        scenario = load_scenario(state.scenario_id)
        return scenario, state
    except FileNotFoundError:
        return None, state


def _room_name(scenario: dict, room_id: str) -> str:
    for r in scenario.get("rooms", []):
        if r["id"] == room_id:
            return r.get("name", room_id)
    return room_id


def _room_data(scenario: dict, room_id: str) -> dict:
    for r in scenario.get("rooms", []):
        if r["id"] == room_id:
            return r
    return {"id": room_id, "name": room_id, "capacity": 0, "available": True}


def _commitment_data(scenario: dict, room_id: str) -> list[dict]:
    """Return all commitments whose original room is room_id."""
    return [c for c in scenario.get("commitments", []) if c.get("room") == room_id]


def _build_incident(sig: Signal, scenario: dict, applied_ids: set[str]) -> OpsIncident:
    try:
        payload = json.loads(sig.payload) if isinstance(sig.payload, str) else sig.payload
    except (json.JSONDecodeError, TypeError):
        payload = {}

    incident_id = payload.get("incident_id", sig.id)
    room_id = payload.get("room", "")
    room_nm = _room_name(scenario, room_id)

    # Check if resolved: a room_change with caused_by == incident_id was applied
    status = "active"
    all_sigs = [
        s for s in _get_all_signals_from_scenario(scenario)
        if s.get("kind") == "room_change"
    ]
    for s in all_sigs:
        sp = s.get("payload", {})
        if sp.get("caused_by") == incident_id and s["id"] in applied_ids:
            status = "resolved"
            break

    return OpsIncident(
        id=incident_id,
        room_id=room_id,
        room_name=room_nm,
        type=payload.get("type", "unknown"),
        temperature_c=payload.get("temperature_c"),
        trend=payload.get("trend"),
        reported_at_utc=_ensure_utc(sig.at_utc),
        status=status,
    )


def _get_all_signals_from_scenario(scenario: dict) -> list[dict]:
    return scenario.get("timeline", [])


# ─── GET /ops/incidents ────────────────────────────────────────────────────────

@router.get("/incidents", response_model=list[OpsIncident])
def list_incidents(db: Session = Depends(get_db)):
    """
    Return OpsIncident objects for all applied building_ops incident signals
    in the current scenario. Returns empty list if no scenario is running.
    """
    scenario, state = _get_scenario(db)
    if scenario is None:
        return []

    try:
        applied_ids = set(json.loads(state.applied_signal_ids))
    except (json.JSONDecodeError, TypeError):
        applied_ids = set()

    incident_signals = (
        db.query(Signal)
        .filter(Signal.feed == "building_ops", Signal.kind == "incident")
        .order_by(Signal.at_utc)
        .all()
    )

    result = []
    for sig in incident_signals:
        if sig.id in applied_ids:
            result.append(_build_incident(sig, scenario, applied_ids))

    return result


# ─── GET /ops/incidents/{incident_id}/impact ──────────────────────────────────

@router.get("/incidents/{incident_id}/impact", response_model=ImpactGraph)
def get_incident_impact(incident_id: str, db: Session = Depends(get_db)):
    """
    Return ImpactGraph for the given incident_id.
    Works even if no scenario is running (returns empty graph, 200 OK).
    """
    now = get_now()
    scenario, state = _get_scenario(db)

    if scenario is None:
        # No scenario: return an empty but valid response
        return ImpactGraph(
            incident=OpsIncident(
                id=incident_id,
                room_id="",
                room_name="Unknown",
                type="unknown",
                temperature_c=None,
                trend=None,
                reported_at_utc=now,
                status="active",
            ),
            affected_classes=[],
            total_students=0,
            feasible_mitigations=[],
            student_effect="No scenario is running.",
        )

    try:
        applied_ids = set(json.loads(state.applied_signal_ids))
    except (json.JSONDecodeError, TypeError):
        applied_ids = set()

    # Find the incident signal
    incident_sig: Optional[Signal] = None
    for sig in db.query(Signal).filter(Signal.feed == "building_ops", Signal.kind == "incident").all():
        try:
            payload = json.loads(sig.payload) if isinstance(sig.payload, str) else sig.payload
        except (json.JSONDecodeError, TypeError):
            payload = {}
        if payload.get("incident_id") == incident_id and sig.id in applied_ids:
            incident_sig = sig
            break

    if incident_sig is None:
        return ImpactGraph(
            incident=OpsIncident(
                id=incident_id,
                room_id="",
                room_name="Unknown",
                type="unknown",
                temperature_c=None,
                trend=None,
                reported_at_utc=now,
                status="active",
            ),
            affected_classes=[],
            total_students=0,
            feasible_mitigations=[],
            student_effect="Incident not found.",
        )

    incident = _build_incident(incident_sig, scenario, applied_ids)

    try:
        inc_payload = json.loads(incident_sig.payload) if isinstance(incident_sig.payload, str) else incident_sig.payload
    except (json.JSONDecodeError, TypeError):
        inc_payload = {}

    incident_room_id = inc_payload.get("room", "")

    # Find commitments that use the affected room (original or currently)
    from app.core.config import settings
    user_id = settings.demo_user_id

    # Find all class events on the anchor date
    from datetime import date, timedelta
    anchor = date.fromisoformat(state.anchor_date)
    anchor_start_naive = datetime(anchor.year, anchor.month, anchor.day, 0, 0)
    anchor_end_naive = datetime(anchor.year, anchor.month, anchor.day, 23, 59)

    class_events = (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.user_id == user_id,
            CalendarEvent.event_type == "class",
            CalendarEvent.source_type.in_(["scenario", "aurora_block"]),
            CalendarEvent.start_at_utc >= anchor_start_naive,
            CalendarEvent.start_at_utc <= anchor_end_naive,
        )
        .all()
    )

    # Build a map from commitment_id to its current CalendarEvent
    cal_ev_by_commitment: dict[str, object] = {
        ev.source_reference: ev
        for ev in class_events
        if ev.source_reference
    }

    # Get the incident room name for comparison
    incident_room_name = _room_name(scenario, incident_room_id)

    # Match commitments where the CURRENT location is the incident room
    # (covers both original assignments AND classes moved there by a room_change signal)
    affected_commitments = []
    for c in scenario.get("commitments", []):
        cal_ev = cal_ev_by_commitment.get(c["id"])
        if cal_ev is None:
            continue
        current_loc = (cal_ev.location_text or "").strip()
        # Match by room id, room name, or original assignment
        if (
            current_loc == incident_room_id
            or current_loc == incident_room_name
            or c.get("room") == incident_room_id
        ):
            affected_commitments.append(c)

    affected_classes: list[AffectedClass] = []
    total_students = 0

    now_local = _ensure_utc(now).astimezone(_CAMPUS_TZ)

    for commitment in affected_commitments:
        c_id = commitment["id"]
        # Find matching calendar event
        cal_ev = cal_ev_by_commitment.get(c_id)
        if cal_ev is None:
            continue

        # Determine current location (may have been room_changed)
        current_room_name = cal_ev.location_text or commitment.get("room", "")

        # Parse start/end times in campus tz
        start_local = _ensure_utc(cal_ev.start_at_utc).astimezone(_CAMPUS_TZ)
        end_local = _ensure_utc(cal_ev.end_at_utc).astimezone(_CAMPUS_TZ)

        cls_status = "in_session" if start_local <= now_local <= end_local else "not_started"

        # Feasible rooms: only for not_started — rooms available, capacity >= enrolled
        enrolled = commitment.get("enrolled", 0)
        feasible_rooms = []
        if cls_status == "not_started":
            for r in scenario.get("rooms", []):
                if (
                    r.get("available", True)
                    and r["id"] != incident_room_id
                    and r.get("capacity", 0) >= enrolled
                    and r.get("kind") == "classroom"
                ):
                    feasible_rooms.append({
                        "room_id": r["id"],
                        "room_name": r.get("name", r["id"]),
                        "capacity": r.get("capacity", 0),
                    })

        affected_classes.append(AffectedClass(
            commitment_id=c_id,
            title=commitment["title"],
            course=commitment.get("course", ""),
            start=start_local.strftime("%I:%M %p"),
            end=end_local.strftime("%I:%M %p"),
            room_name=current_room_name,
            enrolled=enrolled,
            status=cls_status,
            feasible_rooms=feasible_rooms,
        ))
        total_students += enrolled

    # Feasible mitigations: for each not_started class, suggest moving to first feasible room
    feasible_mitigations = []
    for ac in affected_classes:
        if ac.status == "not_started" and ac.feasible_rooms:
            best = ac.feasible_rooms[0]
            feasible_mitigations.append({
                "commitment_id": ac.commitment_id,
                "course": ac.course,
                "room_id": best["room_id"],
                "room_name": best["room_name"],
                "action": "request_room_change",
                "simulated": True,
            })

    # Student-facing effect text
    in_session_titles = [ac.title for ac in affected_classes if ac.status == "in_session"]
    not_started_titles = [ac.title for ac in affected_classes if ac.status == "not_started"]

    effect_parts = []
    if in_session_titles:
        effect_parts.append(
            f"Your {', '.join(in_session_titles)} class is currently in session in the affected room."
        )
    if not_started_titles:
        mits = {m["commitment_id"]: m["room_name"] for m in feasible_mitigations}
        for ac in affected_classes:
            if ac.status == "not_started":
                if ac.commitment_id in mits:
                    effect_parts.append(
                        f"Your {ac.title} class uses {incident.room_name}. "
                        f"If this is resolved, your location may change to {mits[ac.commitment_id]}."
                    )
                else:
                    effect_parts.append(
                        f"Your {ac.title} class uses {incident.room_name}. "
                        f"No feasible replacement room found."
                    )

    student_effect = " ".join(effect_parts) if effect_parts else "No student classes are directly affected."

    return ImpactGraph(
        incident=incident,
        affected_classes=affected_classes,
        total_students=total_students,
        feasible_mitigations=feasible_mitigations,
        student_effect=student_effect,
    )


# ─── POST /ops/incidents/{incident_id}/approve-mitigation ─────────────────────

@router.post("/incidents/{incident_id}/approve-mitigation")
def approve_mitigation(incident_id: str, db: Session = Depends(get_db)):
    """
    Execute a simulated room change for the feasible mitigation of the incident.
    Emits a room_change signal for all not_started affected classes.
    Writes AuditEvent. Returns simulated status.
    No real room change request is sent.
    """
    now = get_now()
    scenario, state = _get_scenario(db)
    if scenario is None:
        raise HTTPException(status_code=400, detail="No scenario is running.")

    try:
        applied_ids = set(json.loads(state.applied_signal_ids))
    except (json.JSONDecodeError, TypeError):
        applied_ids = set()

    # Get impact graph to know what to change
    impact = get_incident_impact(incident_id, db)

    from app.core.config import settings
    user_id = settings.demo_user_id

    changes_made = []
    for mitigation in impact.feasible_mitigations:
        commitment_id = mitigation["commitment_id"]
        new_room_id = mitigation["room_id"]
        new_room_name = mitigation["room_name"]

        # Update the calendar event location
        cal_ev = (
            db.query(CalendarEvent)
            .filter(
                CalendarEvent.user_id == user_id,
                CalendarEvent.source_reference == commitment_id,
            )
            .first()
        )
        if cal_ev:
            cal_ev.location_text = new_room_name
            changes_made.append(f"{mitigation['course']} → {new_room_name}")

        # Create a synthetic room_change signal in the DB (so it appears in signals feed)
        sig_id = f"manual-approval-{incident_id}-{commitment_id}"
        if not db.get(Signal, sig_id):
            new_sig = Signal(
                id=sig_id,
                feed="solar",
                kind="room_change",
                at_utc=now.replace(tzinfo=None) if now.tzinfo else now,
                summary=f"{mitigation['course']} moved to {new_room_name} (staff manual approval)",
                payload=json.dumps({
                    "commitment": commitment_id,
                    "to": new_room_id,
                    "reason": f"Relocated after incident {incident_id} (manual staff approval)",
                    "effective": "today",
                    "caused_by": incident_id,
                    "manual_approval": True,
                }),
                relevance="relevant",
                relevance_reason="Manual staff approval",
                data_origin="synthetic",
                scenario_id=state.scenario_id,
            )
            db.add(new_sig)
            # Mark as applied
            applied_ids.add(sig_id)

    state.applied_signal_ids = json.dumps(list(applied_ids))

    # Write audit event
    audit = AuditEvent(
        user_id=None,
        action="approve_mitigation",
        resource_type="ops_incident",
        resource_id=incident_id,
        result="executed_simulated",
    )
    db.add(audit)
    db.commit()

    return {
        "status": "executed_simulated",
        "message": "Simulated: no real room change request was sent.",
        "changes": changes_made,
    }

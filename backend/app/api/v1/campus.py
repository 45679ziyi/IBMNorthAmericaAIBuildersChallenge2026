"""Campus API — U5-3.

Routes:
  GET /campus/buildings   → list of buildings with deterministic x,y coords
  GET /campus/incidents   → active canonical events of incident type
"""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.tenancy import ActorContext, resolve_actor
from app.db.session import get_db
from app.models.models import CanonicalEvent, SimState
from app.services.campus.scenario import load_scenario

router = APIRouter(prefix="/campus", tags=["campus"])

# ── Coordinate generation (deterministic) ────────────────────────────────────

_BUILDING_KINDS = ("academic", "library", "student_center", "lecture", "admin", "lab")


def _deterministic_xy(building_id: str) -> tuple[float, float]:
    """Generate deterministic (x, y) in 0..100 range from building_id hash."""
    digest = hashlib.sha256(building_id.encode()).digest()
    x = (digest[0] * 256 + digest[1]) % 10000 / 100.0
    y = (digest[2] * 256 + digest[3]) % 10000 / 100.0
    return round(x, 1), round(y, 1)


def _building_kind(name: str) -> str:
    name_lower = name.lower()
    if "library" in name_lower:
        return "library"
    if "activities" in name_lower or "student" in name_lower:
        return "student_center"
    if "lecture" in name_lower or "javits" in name_lower:
        return "lecture"
    if "lab" in name_lower or "engineering" in name_lower:
        return "lab"
    if "admin" in name_lower:
        return "admin"
    return "academic"


# ── Schemas ───────────────────────────────────────────────────────────────────

class BuildingOut(BaseModel):
    id: str
    code: str
    name: str
    x: float
    y: float
    floors: int
    kind: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/buildings", response_model=list[BuildingOut])
def list_buildings(
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Return buildings with deterministic x,y coordinates.

    If a scenario is active, buildings come from the scenario fixture.
    Otherwise, returns a canonical fallback set.
    """
    state = db.get(SimState, 1)
    scenario_buildings: list[dict] = []

    if state and state.mode == "scenario" and state.scenario_id:
        try:
            sc = load_scenario(state.scenario_id)
            scenario_buildings = sc.get("buildings", [])
        except Exception:
            pass

    if not scenario_buildings:
        # Canonical fallback (always present in demo)
        scenario_buildings = [
            {"id": "LE",  "name": "Light Engineering (demo)"},
            {"id": "CS",  "name": "Computer Science Building (demo)"},
            {"id": "MEL", "name": "Melville Library (demo)"},
            {"id": "SAC", "name": "Student Activities Center (demo)"},
            {"id": "JAV", "name": "Javits Lecture Center (demo)"},
        ]

    result = []
    for b in scenario_buildings:
        bid = b.get("id", "UNK")
        name = b.get("name", bid)
        x, y = _deterministic_xy(bid)
        result.append(BuildingOut(
            id=bid,
            code=bid,
            name=name,
            x=x,
            y=y,
            floors=b.get("floors", 3),
            kind=b.get("kind", _building_kind(name)),
        ))

    return result


@router.get("/incidents")
def list_campus_incidents(
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Return active canonical events that are incident-type."""
    events = (
        db.query(CanonicalEvent)
        .filter(
            CanonicalEvent.status == "open",
            CanonicalEvent.type.like("incident%"),
        )
        .order_by(CanonicalEvent.received_at.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "id": e.id,
            "type": e.type,
            "severity": e.severity,
            "status": e.status,
            "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
            "received_at": e.received_at.isoformat(),
            "entity_refs": e.entity_refs_json,
        }
        for e in events
    ]

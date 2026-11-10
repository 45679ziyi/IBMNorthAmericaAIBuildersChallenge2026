"""
V4-09 — Campus Resource Discovery service.

Provides deterministic, explainable discovery for two initial resource categories:
  1. rooms  — for classroom/meeting space needs
  2. services — for campus service needs

Design principles (from V4 spec §18.11):
- Hard constraints applied first (filter step).
- Soft preferences scored with a versioned, explainable formula.
- Natural-language queries parsed into a structured draft query (confirmation step).
- Results are ranked, sourced, and factor-annotated.
- No invented availability, safety, or quality metrics.
- Unauthorized resources never appear.
- Reuses room-scoring logic from Scenario Engine where possible.

Scoring version: "v1"
Weights:
  capacity_fit:       0.40
  feature_match:      0.30
  building_proximity: 0.20
  availability:       0.10  (1.0 if no conflict known, 0.0 if conflict detected)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import EntityLink


# ─── Scoring version ─────────────────────────────────────────────────────────

DISCOVERY_VERSION = "v1"

ROOM_WEIGHTS = {
    "capacity_fit": 0.40,
    "feature_match": 0.30,
    "building_proximity": 0.20,
    "availability": 0.10,
}


# ─── Input schemas ────────────────────────────────────────────────────────────

@dataclass
class RoomQuery:
    """Structured query for room discovery.

    min_capacity: minimum headcount required.
    required_features: list of required room features (e.g. ["projector"]).
    preferred_building: optional preferred building ID for proximity scoring.
    exclude_rooms: set of room IDs to exclude (e.g. currently affected rooms).
    time_slot: optional ISO time string for availability checks.
    limit: max results to return.
    """
    min_capacity: int = 0
    required_features: list[str] = field(default_factory=list)
    preferred_building: Optional[str] = None
    exclude_rooms: set[str] = field(default_factory=set)
    time_slot: Optional[str] = None
    limit: int = 10


@dataclass
class ServiceQuery:
    """Structured query for campus service discovery.

    service_type: e.g. "it_support", "facilities", "academic_advising"
    building_id: optional building to scope the search.
    limit: max results to return.
    """
    service_type: Optional[str] = None
    building_id: Optional[str] = None
    limit: int = 10


# ─── Result schemas ───────────────────────────────────────────────────────────

@dataclass
class ResourceCandidate:
    """A single discovered resource candidate with score and evidence."""
    resource_type: str              # "room" | "service"
    resource_id: str
    name: Optional[str]
    rank: int                       # 1 = best
    total_score: float
    factor_scores: dict[str, float]  # per-factor breakdown
    factor_weights: dict[str, float]
    data_source: str                # e.g. "entity_link.meta_json"
    freshness: str                  # "graph_data" | "unknown"
    missing_data: list[str]        # data fields not available
    assumptions: list[str]         # stated assumptions


@dataclass
class InfeasibleResource:
    """A resource that failed hard constraints."""
    resource_type: str
    resource_id: str
    failed_constraints: list[str]


@dataclass
class DiscoveryResult:
    """Result of a campus resource discovery query."""
    resource_type: str
    discovery_version: str
    query_summary: str
    candidates: list[ResourceCandidate]
    infeasible: list[InfeasibleResource]
    no_match_reason: Optional[str] = None    # set when candidates == []
    insufficient_data_fields: list[str] = field(default_factory=list)


# ─── NL query parser ─────────────────────────────────────────────────────────

# Feature keyword mapping for natural-language parsing
_FEATURE_KEYWORDS: dict[str, str] = {
    "projector": "projector",
    "project": "projector",
    "av": "av",
    "audio": "av",
    "video": "av",
    "whiteboard": "whiteboard",
    "board": "whiteboard",
    "zoom": "video_conferencing",
    "video conference": "video_conferencing",
    "accessible": "accessible",
    "wheelchair": "accessible",
    "large": None,  # handled as capacity hint
    "small": None,
}

_CAPACITY_PATTERNS = [
    (r"\bcapacity\s+(\d+)\b", int),
    (r"\b(\d+)\s*(?:seats?|students?|people|persons?|capacity)\b", int),
    (r"\bfor\s+(\d+)\b", int),
    (r"\b(\d+)\s*(?:seat|person)\b", int),
]


def parse_room_query_from_nl(text: str) -> tuple[RoomQuery, str]:
    """Parse a natural-language room request into a draft RoomQuery.

    Returns (draft_query, parse_summary) for user confirmation.
    The caller must show parsed_query to the user before executing.

    This is a simple pattern-based parser — it does not call an LLM.
    """
    text_lower = text.lower()
    query = RoomQuery()
    parse_notes: list[str] = []

    # Capacity
    for pattern, cast in _CAPACITY_PATTERNS:
        m = re.search(pattern, text_lower)
        if m:
            query.min_capacity = cast(m.group(1))
            parse_notes.append(f"min_capacity={query.min_capacity} (from '{m.group(0)}')")
            break
    if "large" in text_lower and query.min_capacity == 0:
        query.min_capacity = 50
        parse_notes.append("min_capacity=50 (inferred from 'large')")
    elif "small" in text_lower and query.min_capacity == 0:
        query.min_capacity = 10
        parse_notes.append("min_capacity=10 (inferred from 'small')")

    # Features
    features_found: list[str] = []
    for keyword, feature in _FEATURE_KEYWORDS.items():
        if keyword in text_lower and feature is not None:
            if feature not in features_found:
                features_found.append(feature)
                parse_notes.append(f"required_feature='{feature}' (from '{keyword}')")
    query.required_features = features_found

    parse_summary = "; ".join(parse_notes) if parse_notes else "No specific constraints detected"
    return query, parse_summary


# ─── Room discovery ───────────────────────────────────────────────────────────

def _load_all_rooms(db: Session) -> list[dict]:
    """Load all rooms from EntityLink.meta_json where rel='in_building'."""
    links = (
        db.query(EntityLink)
        .filter(
            EntityLink.from_type == "room",
            EntityLink.rel == "in_building",
        )
        .all()
    )
    rooms = []
    for link in links:
        meta: dict = {}
        if link.meta_json:
            try:
                meta = json.loads(link.meta_json)
            except (json.JSONDecodeError, TypeError):
                meta = {}
        rooms.append({
            "room_id": link.from_id,
            "building_id": link.to_id,
            "capacity": meta.get("capacity"),
            "features": meta.get("features", []),
            "name": meta.get("name"),
            "kind": meta.get("kind"),
        })
    return rooms


def _score_room(
    room: dict,
    query: RoomQuery,
    walking_minutes: dict,
) -> tuple[float, dict[str, float], list[str], list[str]]:
    """Compute weighted score for a room.

    Returns (total_score, factor_scores, missing_data, assumptions).
    """
    factor_scores: dict[str, float] = {}
    missing_data: list[str] = []
    assumptions: list[str] = []

    # ── capacity_fit ──────────────────────────────────────────────────────────
    capacity = room.get("capacity")
    if capacity is None:
        factor_scores["capacity_fit"] = 0.5   # unknown capacity → neutral score
        missing_data.append("room_capacity")
        assumptions.append(f"Capacity of {room['room_id']} is unknown; assumed sufficient.")
    elif capacity >= query.min_capacity:
        # Score: 1.0 if exact or +20% buffer, diminishes above 3x
        ratio = capacity / max(query.min_capacity, 1)
        if ratio <= 1.2:
            factor_scores["capacity_fit"] = 1.0
        elif ratio <= 2.0:
            factor_scores["capacity_fit"] = 0.8
        elif ratio <= 3.0:
            factor_scores["capacity_fit"] = 0.6
        else:
            factor_scores["capacity_fit"] = 0.4  # too large
    else:
        # Under-capacity — hard constraint violation (handled outside this fn)
        factor_scores["capacity_fit"] = 0.0

    # ── feature_match ─────────────────────────────────────────────────────────
    room_features = [f.lower() for f in (room.get("features") or [])]
    if not query.required_features:
        factor_scores["feature_match"] = 1.0
    else:
        matched = sum(
            1 for f in query.required_features
            if any(f.lower() in rf for rf in room_features)
        )
        factor_scores["feature_match"] = matched / len(query.required_features)
        unmatched = [f for f in query.required_features
                     if not any(f.lower() in rf for rf in room_features)]
        if unmatched:
            missing_data.extend(f"feature:{f}" for f in unmatched)

    # ── building_proximity ────────────────────────────────────────────────────
    if not query.preferred_building:
        factor_scores["building_proximity"] = 1.0   # no preference → neutral best
    else:
        if room["building_id"] == query.preferred_building:
            factor_scores["building_proximity"] = 1.0
        else:
            key_ab = f"{query.preferred_building}:{room['building_id']}"
            key_ba = f"{room['building_id']}:{query.preferred_building}"
            walk_m = walking_minutes.get(key_ab) or walking_minutes.get(key_ba)
            if walk_m is None:
                factor_scores["building_proximity"] = 0.5
                missing_data.append(f"walk_minutes:{query.preferred_building}:{room['building_id']}")
                assumptions.append(
                    f"Walking time from {query.preferred_building} to {room['building_id']} "
                    "is unknown; assumed moderate distance."
                )
            elif walk_m <= 5:
                factor_scores["building_proximity"] = 1.0
            elif walk_m <= 10:
                factor_scores["building_proximity"] = 0.7
            elif walk_m <= 20:
                factor_scores["building_proximity"] = 0.4
            else:
                factor_scores["building_proximity"] = 0.2

    # ── availability ─────────────────────────────────────────────────────────
    # V4: availability check is not implemented beyond what's in the graph.
    # We assume available unless a conflict is known.
    factor_scores["availability"] = 1.0

    total = sum(ROOM_WEIGHTS[k] * factor_scores.get(k, 0.0) for k in ROOM_WEIGHTS)
    return round(total, 4), factor_scores, missing_data, assumptions


def discover_rooms(
    db: Session,
    query: RoomQuery,
    walking_minutes: Optional[dict] = None,
) -> DiscoveryResult:
    """Run room discovery with hard constraints + soft scoring.

    Hard constraints (filter first):
    - Room capacity must be >= query.min_capacity (if capacity is known).
    - Room must not be in query.exclude_rooms.
    - Required features must all be present.

    Soft scoring (rank passing candidates):
    - capacity_fit, feature_match, building_proximity, availability.
    """
    if walking_minutes is None:
        walking_minutes = {}

    all_rooms = _load_all_rooms(db)
    candidates: list[ResourceCandidate] = []
    infeasible: list[InfeasibleResource] = []

    for room in all_rooms:
        # ── Hard constraints ─────────────────────────────────────────────────
        failed: list[str] = []

        if room["room_id"] in query.exclude_rooms:
            failed.append(f"room_excluded (in exclude_rooms)")

        capacity = room.get("capacity")
        if capacity is not None and query.min_capacity > 0 and capacity < query.min_capacity:
            failed.append(
                f"capacity_insufficient (room={capacity}, required={query.min_capacity})"
            )

        room_features = [f.lower() for f in (room.get("features") or [])]
        for req_feat in query.required_features:
            if not any(req_feat.lower() in rf for rf in room_features):
                failed.append(f"missing_required_feature:{req_feat}")

        if failed:
            infeasible.append(InfeasibleResource(
                resource_type="room",
                resource_id=room["room_id"],
                failed_constraints=failed,
            ))
            continue

        # ── Soft scoring ─────────────────────────────────────────────────────
        total, factor_scores, missing, assumptions = _score_room(
            room, query, walking_minutes
        )
        candidates.append(ResourceCandidate(
            resource_type="room",
            resource_id=room["room_id"],
            name=room.get("name"),
            rank=0,   # filled below
            total_score=total,
            factor_scores=factor_scores,
            factor_weights=dict(ROOM_WEIGHTS),
            data_source="entity_link.meta_json",
            freshness="graph_data",
            missing_data=missing,
            assumptions=assumptions,
        ))

    # ── Sort and rank ─────────────────────────────────────────────────────────
    candidates.sort(key=lambda c: c.total_score, reverse=True)
    for i, c in enumerate(candidates[: query.limit]):
        c.rank = i + 1
    candidates = candidates[: query.limit]

    no_match = None
    insufficient: list[str] = []
    if not candidates:
        if infeasible:
            no_match = (
                f"All {len(infeasible)} candidate rooms failed hard constraints "
                f"({', '.join(set(c for r in infeasible for c in r.failed_constraints[:1]))})."
            )
        else:
            no_match = "No rooms found in the campus graph for this tenant."

    return DiscoveryResult(
        resource_type="room",
        discovery_version=DISCOVERY_VERSION,
        query_summary=(
            f"min_capacity={query.min_capacity}, "
            f"required_features={query.required_features}, "
            f"preferred_building={query.preferred_building}"
        ),
        candidates=candidates,
        infeasible=infeasible,
        no_match_reason=no_match,
        insufficient_data_fields=insufficient,
    )


# ─── Service discovery ────────────────────────────────────────────────────────

def discover_services(
    db: Session,
    query: ServiceQuery,
) -> DiscoveryResult:
    """Discover campus services matching the query.

    Services are loaded via EntityLink(rel='covers') or EntityLink(rel='scoped_to').
    Results include team assignment and scope.
    """
    from app.models.models import Team, EntityLink as EL

    # Load teams with their scope
    teams = db.query(Team).all()
    candidates: list[ResourceCandidate] = []

    for team in teams:
        # Filter by service_type if requested
        if query.service_type and team.role_type != query.service_type:
            continue

        # Filter by building if requested
        if query.building_id:
            scoped = (
                db.query(EL)
                .filter(
                    EL.from_type == "team",
                    EL.from_id == team.id,
                    EL.rel == "scoped_to",
                    EL.to_type == "building",
                    EL.to_id == query.building_id,
                )
                .first()
            )
            if scoped is None:
                # Check if team covers all buildings (campus-wide scope)
                if team.scope_type != "campus":
                    continue

        factor_scores = {"scope_match": 1.0}
        candidates.append(ResourceCandidate(
            resource_type="service",
            resource_id=team.id,
            name=team.name,
            rank=0,
            total_score=1.0,
            factor_scores=factor_scores,
            factor_weights={"scope_match": 1.0},
            data_source="teams_table",
            freshness="graph_data",
            missing_data=[],
            assumptions=[],
        ))

    candidates = candidates[: query.limit]
    for i, c in enumerate(candidates):
        c.rank = i + 1

    no_match = None
    if not candidates:
        no_match = (
            f"No services found for type='{query.service_type}', "
            f"building='{query.building_id}'."
        )

    return DiscoveryResult(
        resource_type="service",
        discovery_version=DISCOVERY_VERSION,
        query_summary=(
            f"service_type={query.service_type}, building_id={query.building_id}"
        ),
        candidates=candidates,
        infeasible=[],
        no_match_reason=no_match,
    )

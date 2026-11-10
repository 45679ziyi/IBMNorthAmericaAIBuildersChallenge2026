"""Campus Scenario Engine — V4-05.

Deterministic what-if simulation for classroom outage scenarios.
No LLM involvement in computation. LLMs may explain outputs but must
not invent inputs, constraints, or numerical results.

Engine version: v1
Scenario type: classroom_outage

Inputs (ClassroomOutageInput):
  - affected_room_id: the room that is unavailable
  - repair_delay_minutes: how long the room will be unavailable (≥0)
  - requirements: optional overrides (min_capacity, required_features)
  - context_event_version: the canonical_event.version at run time (stale detection)

Hard constraints (must all pass to be feasible):
  HC-1: candidate room capacity ≥ max(affected_section.enrolled, requirements.min_capacity)
  HC-2: candidate room has no conflicting meeting in the affected time window
  HC-3: candidate room is available (EntityLink.meta_json.available is not False)
  HC-4: candidate room is not the affected room itself
  HC-5: candidate room is of kind "classroom" (or kind in requirements.accepted_kinds)

Soft score factors (higher = better, all between 0.0 and 1.0):
  SF-1: capacity_fit  = enrolled / candidate.capacity  (closer to 1.0 = better fit)
  SF-2: building_proximity = 1 / (1 + distance)  using walk_minutes from TenantConfig
  SF-3: feature_match = matched_features / required_features  (if requirements.required_features)
  SF-4: same_building = 1.0 if same building else 0.0

Weights (engine_version=v1): [capacity_fit=0.4, building_proximity=0.3, feature_match=0.2, same_building=0.1]

Output (ScenarioResult):
  - scenario_id: unique run ID
  - engine_version: "v1"
  - scenario_type: "classroom_outage"
  - inputs: echo of ClassroomOutageInput
  - candidates: list[CandidateOption] (feasible, ranked best first)
  - infeasible: list[InfeasibleOption] (failed ≥1 hard constraint, with explanation)
  - affected_sections: list[AffectedSection]
  - summary: dict with counts and aggregate facts
  - missing_data: list[str] — data fields that could not be resolved
  - assumptions: list[str] — assumptions made when data was missing
  - result_hash: sha256 of deterministic canonical form
  - data_origin: "synthetic_simulation"
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import CanonicalEvent, EntityLink, TenantConfig
from app.services.authz import suppress_small_count


ENGINE_VERSION = "v1"
SCENARIO_TYPE = "classroom_outage"

# Soft-score weights (must sum to 1.0)
_WEIGHTS = {
    "capacity_fit":         0.4,
    "building_proximity":   0.3,
    "feature_match":        0.2,
    "same_building":        0.1,
}

_DEFAULT_MIN_CELL = 5
_MAX_WALK_MINUTES_FALLBACK = 15  # used when walk_minutes is unknown


# ── Input / Output schemas ─────────────────────────────────────────────────────

@dataclass
class ClassroomOutageInput:
    """Typed input for a classroom outage scenario."""
    affected_room_id: str
    repair_delay_minutes: int          # 0 = unknown/indefinite
    min_capacity: Optional[int] = None  # if None, use enrolled headcount
    required_features: list[str] = field(default_factory=list)
    accepted_kinds: list[str] = field(default_factory=lambda: ["classroom"])
    context_event_version: Optional[int] = None  # for stale detection


@dataclass
class ScoreFactors:
    """Per-factor score breakdown for transparency."""
    capacity_fit: float
    building_proximity: float
    feature_match: float
    same_building: float
    total: float
    capacity_fit_basis: str        # e.g. "enrolled=28 / candidate=35"
    proximity_basis: str           # e.g. "walk_minutes=3" or "unknown"
    feature_match_basis: str       # e.g. "2/3 required features present"
    missing_data: list[str] = field(default_factory=list)


@dataclass
class CandidateOption:
    """A feasible room alternative with score and explanation."""
    option_id: str                  # stable: "opt_{room_id}"
    room_id: str
    room_name: str
    building_id: str
    capacity: int
    features: list[str]
    rank: int                       # 1 = best
    score: float                    # total soft score 0.0–1.0
    score_factors: ScoreFactors
    data_origin: str = "synthetic_simulation"


@dataclass
class InfeasibleOption:
    """A room that failed one or more hard constraints."""
    room_id: str
    room_name: str
    failed_constraints: list[str]   # e.g. ["HC-1: capacity too small (need 28, have 20)"]


@dataclass
class AffectedSection:
    """A class meeting that cannot proceed in the affected room."""
    section_id: str
    course_id: str
    enrolled: int
    enrolled_display: str           # suppress_small_count applied
    meeting_days: list[str]
    meeting_start: str
    meeting_end: str
    affected_meetings_in_window: int


@dataclass
class ScenarioResult:
    """Complete output of one scenario run."""
    scenario_id: str
    engine_version: str
    scenario_type: str
    inputs: dict
    candidates: list[CandidateOption]
    infeasible: list[InfeasibleOption]
    affected_sections: list[AffectedSection]
    summary: dict
    missing_data: list[str]
    assumptions: list[str]
    result_hash: str
    data_origin: str = "synthetic_simulation"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_room_meta(db: Session, room_id: str) -> Optional[dict]:
    """Load room attributes from EntityLink.meta_json (in_building link)."""
    link = (
        db.query(EntityLink)
        .filter(
            EntityLink.from_type == "room",
            EntityLink.from_id == room_id,
            EntityLink.rel == "in_building",
        )
        .first()
    )
    if link is None:
        return None
    if link.meta_json:
        try:
            return json.loads(link.meta_json)
        except (json.JSONDecodeError, TypeError):
            pass
    return {"capacity": None, "features": [], "name": room_id, "kind": "classroom",
            "available": True}


def _load_meetings_in_room(db: Session, room_id: str) -> list[dict]:
    """Load section meetings scheduled in a room."""
    links = (
        db.query(EntityLink)
        .filter(
            EntityLink.to_type == "room",
            EntityLink.to_id == room_id,
            EntityLink.rel == "meets_in",
        )
        .all()
    )
    results = []
    for link in links:
        meta = {}
        if link.meta_json:
            try:
                meta = json.loads(link.meta_json)
            except (json.JSONDecodeError, TypeError):
                pass
        results.append({"section_id": link.from_id, **meta})
    return results


def _load_affected_sections(db: Session, room_id: str) -> list[dict]:
    """Load sections that currently meet in the affected room."""
    return _load_meetings_in_room(db, room_id)


def _time_to_minutes(t: str) -> int:
    """Convert 'HH:MM' to minutes from midnight."""
    if not t:
        return 0
    try:
        h, m = t.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 0


def _meetings_overlap(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    """True if two time windows overlap."""
    a0, a1 = _time_to_minutes(a_start), _time_to_minutes(a_end)
    b0, b1 = _time_to_minutes(b_start), _time_to_minutes(b_end)
    return a0 < b1 and b0 < a1


def _walk_minutes(db: Session, from_building: str, to_building: str) -> Optional[int]:
    """Look up walking time between buildings from TenantConfig.extra_json."""
    if from_building == to_building:
        return 0
    cfg = db.query(TenantConfig).first()
    if cfg and cfg.extra_json:
        try:
            extra = json.loads(cfg.extra_json)
            wm = extra.get("walking_minutes", {})
            # Try both directions
            key1 = f"{from_building}:{to_building}"
            key2 = f"{to_building}:{from_building}"
            if key1 in wm:
                return wm[key1]
            if key2 in wm:
                return wm[key2]
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def _all_rooms(db: Session) -> list[tuple[str, str]]:
    """Return (room_id, building_id) for all known rooms."""
    links = (
        db.query(EntityLink)
        .filter(
            EntityLink.from_type == "room",
            EntityLink.rel == "in_building",
        )
        .all()
    )
    return [(link.from_id, link.to_id) for link in links]


def _affected_building(db: Session, room_id: str) -> Optional[str]:
    link = (
        db.query(EntityLink)
        .filter(
            EntityLink.from_type == "room",
            EntityLink.from_id == room_id,
            EntityLink.rel == "in_building",
        )
        .first()
    )
    return link.to_id if link else None


# ── Hard constraint checkers ──────────────────────────────────────────────────

def _check_hard_constraints(
    room_id: str,
    room_meta: dict,
    affected_sections: list[dict],
    inputs: ClassroomOutageInput,
) -> list[str]:
    """Return list of failed hard constraint descriptions (empty = feasible)."""
    failed = []
    capacity = room_meta.get("capacity")

    # HC-4: not the affected room itself
    if room_id == inputs.affected_room_id:
        failed.append(f"HC-4: this is the affected room ({room_id})")
        return failed  # short-circuit

    # HC-5: kind check
    kind = room_meta.get("kind", "classroom")
    if kind not in inputs.accepted_kinds:
        failed.append(f"HC-5: room kind '{kind}' not in accepted {inputs.accepted_kinds}")

    # HC-3: availability
    if room_meta.get("available") is False:
        failed.append("HC-3: room is marked unavailable")

    # HC-1: capacity
    max_enrolled = max(
        (s.get("enrolled", 0) for s in affected_sections),
        default=0
    )
    required_cap = max(
        inputs.min_capacity or 0,
        max_enrolled,
    )
    if capacity is None:
        # missing data — we don't fail hard on unknown capacity
        pass
    elif capacity < required_cap:
        failed.append(
            f"HC-1: capacity too small (need {required_cap}, room has {capacity})"
        )

    # HC-2: time conflict — check if candidate room already has a meeting at the same time
    # For each affected section meeting, check if the candidate room has a meeting that overlaps
    candidate_meetings = _load_meetings_in_room_by_id_memo.get(room_id, [])
    for aff_sec in affected_sections:
        for aff_day in aff_sec.get("days", []):
            for cand_meeting in candidate_meetings:
                if aff_day in cand_meeting.get("days", []):
                    if _meetings_overlap(
                        aff_sec.get("start", ""), aff_sec.get("end", ""),
                        cand_meeting.get("start", ""), cand_meeting.get("end", "")
                    ):
                        failed.append(
                            f"HC-2: time conflict on {aff_day} "
                            f"{aff_sec.get('start')}–{aff_sec.get('end')} "
                            f"with existing meeting in {room_id}"
                        )

    return failed


# Module-level memo for meeting lookups within a single engine.run() call
_load_meetings_in_room_by_id_memo: dict[str, list[dict]] = {}


# ── Soft score computation ─────────────────────────────────────────────────────

def _compute_soft_score(
    room_id: str,
    room_meta: dict,
    building_id: str,
    affected_building_id: Optional[str],
    affected_sections: list[dict],
    inputs: ClassroomOutageInput,
    db: Session,
) -> ScoreFactors:
    missing_data: list[str] = []
    capacity = room_meta.get("capacity")
    features = room_meta.get("features", [])

    # SF-1: capacity fit (prefer room that fits well without being oversized)
    max_enrolled = max((s.get("enrolled", 0) for s in affected_sections), default=0)
    if capacity and capacity > 0 and max_enrolled > 0:
        fit = min(max_enrolled / capacity, 1.0)
        cap_basis = f"enrolled={max_enrolled} / capacity={capacity}"
    elif capacity and capacity > 0:
        fit = 0.5  # unknown enrolled
        cap_basis = f"enrolled=unknown, capacity={capacity}"
        missing_data.append("section.enrolled")
    else:
        fit = 0.5  # unknown capacity
        cap_basis = "capacity unknown"
        missing_data.append("room.capacity")

    # SF-2: building proximity
    walk = None
    if affected_building_id:
        walk = _walk_minutes(db, affected_building_id, building_id)
    if walk is None:
        prox = 0.5  # neutral when unknown
        prox_basis = "walk_minutes unknown (using neutral 0.5)"
        missing_data.append("walk_minutes")
    else:
        prox = 1.0 / (1.0 + walk / 5.0)  # 5-min walk → ~0.5
        prox_basis = f"walk_minutes={walk}"

    # SF-3: feature match
    required = inputs.required_features
    if required:
        matched = sum(1 for f in required if f in features)
        feat_score = matched / len(required)
        feat_basis = f"{matched}/{len(required)} required features present"
    else:
        feat_score = 1.0
        feat_basis = "no required features specified"

    # SF-4: same building bonus
    same = 1.0 if (affected_building_id and building_id == affected_building_id) else 0.0

    total = (
        _WEIGHTS["capacity_fit"] * fit
        + _WEIGHTS["building_proximity"] * prox
        + _WEIGHTS["feature_match"] * feat_score
        + _WEIGHTS["same_building"] * same
    )

    return ScoreFactors(
        capacity_fit=round(fit, 4),
        building_proximity=round(prox, 4),
        feature_match=round(feat_score, 4),
        same_building=same,
        total=round(total, 4),
        capacity_fit_basis=cap_basis,
        proximity_basis=prox_basis,
        feature_match_basis=feat_basis,
        missing_data=missing_data,
    )


# ── Result hashing ────────────────────────────────────────────────────────────

def _hash_result(inputs: ClassroomOutageInput, candidates: list[CandidateOption],
                  infeasible: list[InfeasibleOption]) -> str:
    """Deterministic sha256 of the canonical result representation."""
    canonical = {
        "engine_version": ENGINE_VERSION,
        "inputs": {
            "affected_room_id": inputs.affected_room_id,
            "repair_delay_minutes": inputs.repair_delay_minutes,
            "min_capacity": inputs.min_capacity,
            "required_features": sorted(inputs.required_features),
            "accepted_kinds": sorted(inputs.accepted_kinds),
        },
        "candidate_room_ids": [c.room_id for c in candidates],
        "infeasible_room_ids": sorted([i.room_id for i in infeasible]),
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Main engine ───────────────────────────────────────────────────────────────

class ScenarioEngine:
    """Deterministic classroom outage scenario engine. No LLM dependency."""

    version = ENGINE_VERSION

    def run(
        self,
        db: Session,
        inputs: ClassroomOutageInput,
        scenario_id: str,
        min_cell_size: int = _DEFAULT_MIN_CELL,
    ) -> ScenarioResult:
        """Run the scenario and return a ScenarioResult.

        Does NOT write to canonical tables. The caller is responsible for
        persisting the ScenarioRun record.
        """
        global _load_meetings_in_room_by_id_memo
        _load_meetings_in_room_by_id_memo = {}  # reset memo for this run

        missing_data: list[str] = []
        assumptions: list[str] = []

        # ── 1. Load affected sections ──────────────────────────────────────
        raw_affected = _load_affected_sections(db, inputs.affected_room_id)
        if not raw_affected:
            missing_data.append(f"no section meetings found in room {inputs.affected_room_id}")
            assumptions.append("proceeding with zero affected sections — room may be empty")

        # ── 2. Build AffectedSection objects ──────────────────────────────
        affected_sections: list[AffectedSection] = []
        for m in raw_affected:
            enrolled_raw = m.get("enrolled", 0)
            enrolled_disp = suppress_small_count(enrolled_raw, min_cell_size)
            affected_sections.append(AffectedSection(
                section_id=m.get("section_id", "unknown"),
                course_id=m.get("course_id", "unknown"),
                enrolled=enrolled_raw,
                enrolled_display=str(enrolled_disp),
                meeting_days=m.get("days", []),
                meeting_start=m.get("start", ""),
                meeting_end=m.get("end", ""),
                affected_meetings_in_window=1,  # conservative: each slot is one meeting
            ))

        # ── 3. Load all candidate rooms ────────────────────────────────────
        all_rooms = _all_rooms(db)
        if not all_rooms:
            missing_data.append("no rooms found in tenant data")
            assumptions.append("empty candidate list — tenant rooms not loaded")

        affected_building_id = _affected_building(db, inputs.affected_room_id)
        if affected_building_id is None:
            missing_data.append(f"building for room {inputs.affected_room_id} unknown")
            assumptions.append("building proximity scores set to neutral 0.5")

        # Pre-load candidate meeting schedules into memo (avoids N+1)
        for room_id, _ in all_rooms:
            _load_meetings_in_room_by_id_memo[room_id] = _load_meetings_in_room(db, room_id)

        # ── 4. Evaluate each candidate ────────────────────────────────────
        candidates: list[CandidateOption] = []
        infeasible: list[InfeasibleOption] = []

        for room_id, building_id in all_rooms:
            meta = _load_room_meta(db, room_id)
            if meta is None:
                meta = {"capacity": None, "features": [], "name": room_id,
                        "kind": "classroom", "available": True}
                missing_data.append(f"room meta missing for {room_id}")

            failed = _check_hard_constraints(
                room_id, meta, raw_affected, inputs
            )

            if failed:
                infeasible.append(InfeasibleOption(
                    room_id=room_id,
                    room_name=meta.get("name", room_id),
                    failed_constraints=failed,
                ))
                continue

            factors = _compute_soft_score(
                room_id, meta, building_id,
                affected_building_id, raw_affected, inputs, db,
            )
            if factors.missing_data:
                for md in factors.missing_data:
                    if md not in missing_data:
                        missing_data.append(md)

            candidates.append(CandidateOption(
                option_id=f"opt_{room_id}",
                room_id=room_id,
                room_name=meta.get("name", room_id),
                building_id=building_id,
                capacity=meta.get("capacity") or 0,
                features=meta.get("features", []),
                rank=0,  # assigned after sort
                score=factors.total,
                score_factors=factors,
            ))

        # ── 5. Sort and rank ──────────────────────────────────────────────
        # Secondary sort by room_id for determinism when scores are equal
        candidates.sort(key=lambda c: (-c.score, c.room_id))
        for i, c in enumerate(candidates):
            c.rank = i + 1

        # ── 6. Result hash ────────────────────────────────────────────────
        result_hash = _hash_result(inputs, candidates, infeasible)

        # ── 7. Summary ───────────────────────────────────────────────────
        total_enrolled = sum(s.enrolled for s in affected_sections)
        summary = {
            "affected_sections_count": len(affected_sections),
            "affected_students_display": str(suppress_small_count(total_enrolled, min_cell_size)),
            "feasible_alternatives": len(candidates),
            "infeasible_rooms_checked": len(infeasible),
            "repair_delay_minutes": inputs.repair_delay_minutes,
            "best_option_id": candidates[0].option_id if candidates else None,
            "data_completeness": "partial" if missing_data else "complete",
        }

        return ScenarioResult(
            scenario_id=scenario_id,
            engine_version=ENGINE_VERSION,
            scenario_type=SCENARIO_TYPE,
            inputs=asdict(inputs),
            candidates=candidates,
            infeasible=infeasible,
            affected_sections=affected_sections,
            summary=summary,
            missing_data=missing_data,
            assumptions=assumptions,
            result_hash=result_hash,
        )


# Module-level singleton
engine = ScenarioEngine()

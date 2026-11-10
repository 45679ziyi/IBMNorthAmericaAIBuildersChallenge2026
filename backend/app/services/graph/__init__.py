"""Campus entity graph service — U3 / V4-02.

Provides:
  neighbors(db, from_type, from_id, rel) -> list[dict]
  impact_of(db, entity_type, entity_id) -> dict
  audience_for(db, canonical_event) -> dict

V4-02 changes:
  - audience_for() now resolves Facilities/IT via 'scoped_to' EntityLinks
    (team → scoped_to → building|service) rather than role-wide Person queries.
  - Faculty resolved via 'taught_by' (pack) or 'teaches' (legacy) links.
  - No entity-ref fallback: empty entity_refs → empty audience, not all-role.
  - Empty audience NEVER equals allow-all. Callers must handle unresolved scope.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import EntityLink, Person, TeamMembership, CanonicalEvent


# ── neighbors ─────────────────────────────────────────────────────────────────

def neighbors(
    db: Session,
    from_type: str,
    from_id: str,
    rel: Optional[str] = None,
) -> list[dict]:
    """Return all entities that are directly linked from (from_type, from_id).

    If rel is provided, restrict to links of that relationship type.
    Each dict has keys: type, id, rel.
    """
    q = db.query(EntityLink).filter(
        EntityLink.from_type == from_type,
        EntityLink.from_id == from_id,
    )
    if rel is not None:
        q = q.filter(EntityLink.rel == rel)
    return [{"type": link.to_type, "id": link.to_id, "rel": link.rel} for link in q.all()]


def _reverse_neighbors(
    db: Session,
    to_type: str,
    to_id: str,
    rel: Optional[str] = None,
) -> list[dict]:
    """Return all entities that link TO (to_type, to_id)."""
    q = db.query(EntityLink).filter(
        EntityLink.to_type == to_type,
        EntityLink.to_id == to_id,
    )
    if rel is not None:
        q = q.filter(EntityLink.rel == rel)
    return [{"type": link.from_type, "id": link.from_id, "rel": link.rel} for link in q.all()]


# ── impact_of ─────────────────────────────────────────────────────────────────

def impact_of(
    db: Session,
    entity_type: str,
    entity_id: str,
) -> dict:
    """Compute the impact of an entity failure / disruption.

    Traverses entity_links to find affected sections, headcount, buildings,
    services, and which persona roles are affected.

    Returns:
        {
          sections: list[str],       # section IDs
          headcount: int,            # total enrolled headcount
          buildings: list[str],      # building IDs
          services: list[str],       # service IDs
          affected_personas: list[str]   # role types
        }
    """
    sections: set[str] = set()
    buildings: set[str] = set()
    services: set[str] = set()

    if entity_type == "room":
        # Room → section (holds_section), building (in_building)
        for n in neighbors(db, "room", entity_id, "holds_section"):
            sections.add(n["id"])
        for n in neighbors(db, "room", entity_id, "in_building"):
            buildings.add(n["id"])
        # Also sections that use the room
        for link in db.query(EntityLink).filter(
            EntityLink.to_type == "room",
            EntityLink.to_id == entity_id,
            EntityLink.rel == "uses_room",
        ).all():
            sections.add(link.from_id)
        # meets_in links from pack loader (section → meets_in → room)
        for link in db.query(EntityLink).filter(
            EntityLink.to_type == "room",
            EntityLink.to_id == entity_id,
            EntityLink.rel == "meets_in",
        ).all():
            sections.add(link.from_id)

    elif entity_type == "building":
        buildings.add(entity_id)
        # All rooms in this building → all sections in those rooms
        for room_link in db.query(EntityLink).filter(
            EntityLink.to_type == "building",
            EntityLink.to_id == entity_id,
            EntityLink.rel == "in_building",
        ).all():
            room_id = room_link.from_id
            for sec_link in db.query(EntityLink).filter(
                EntityLink.from_type == "room",
                EntityLink.from_id == room_id,
                EntityLink.rel.in_(["holds_section"]),
            ).all():
                sections.add(sec_link.to_id)
            for sec_link in db.query(EntityLink).filter(
                EntityLink.to_type == "room",
                EntityLink.to_id == room_id,
                EntityLink.rel.in_(["uses_room", "meets_in"]),
            ).all():
                sections.add(sec_link.from_id)

    elif entity_type == "service":
        services.add(entity_id)
        # Services can affect all buildings and sections (campus-wide)
        for link in db.query(EntityLink).filter(
            EntityLink.to_type == "service",
            EntityLink.to_id == entity_id,
        ).all():
            if link.from_type == "building":
                buildings.add(link.from_id)
            elif link.from_type == "section":
                sections.add(link.from_id)

    elif entity_type == "section":
        sections.add(entity_id)
        # Find the room used by this section
        for link in neighbors(db, "section", entity_id, "uses_room"):
            for n in neighbors(db, "room", link["id"], "in_building"):
                buildings.add(n["id"])
        for link in neighbors(db, "section", entity_id, "meets_in"):
            for n in neighbors(db, "room", link["id"], "in_building"):
                buildings.add(n["id"])

    # Compute headcount from enrollment links on sections
    headcount = 0
    for sec_id in sections:
        enrollment_links = db.query(EntityLink).filter(
            EntityLink.to_type == "section",
            EntityLink.to_id == sec_id,
            EntityLink.rel == "enrolled_in",
        ).count()
        headcount += enrollment_links

    # Determine affected personas
    affected_personas: list[str] = []
    if sections:
        affected_personas.extend(["student", "faculty"])
    if buildings:
        affected_personas.append("facilities")
    if services:
        affected_personas.extend(["it", "facilities"])
    if sections or buildings or services:
        affected_personas.append("academic_ops")
    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for p in affected_personas:
        if p not in seen:
            seen.add(p)
            deduped.append(p)

    return {
        "sections": sorted(sections),
        "headcount": headcount,
        "buildings": sorted(buildings),
        "services": sorted(services),
        "affected_personas": deduped,
    }


# ── audience_for helpers ───────────────────────────────────────────────────────

def _team_members_scoped_to(db: Session, entity_type: str, entity_id: str) -> list[str]:
    """Return person IDs on teams that are explicitly scoped to entity_type/entity_id.

    V4-02 (Finding C): resolves team responsibility via the 'scoped_to' EntityLink
    created by the pack loader.  Only members of explicitly responsible teams are
    returned; no role-wide fallback.
    """
    team_links = db.query(EntityLink).filter(
        EntityLink.from_type == "team",
        EntityLink.rel == "scoped_to",
        EntityLink.to_type == entity_type,
        EntityLink.to_id == entity_id,
    ).all()
    person_ids: set[str] = set()
    for tl in team_links:
        members = db.query(TeamMembership).filter(
            TeamMembership.team_id == tl.from_id
        ).all()
        for m in members:
            person_ids.add(m.person_id)
    return list(person_ids)


# ── audience_for ──────────────────────────────────────────────────────────────

def audience_for(
    db: Session,
    canonical_event: "CanonicalEvent",
) -> dict:
    """Compute the audience for a canonical event.

    V4-02 (Finding C): resolves audience via explicit 'scoped_to' team
    relationships rather than role-wide fallbacks.

    - Facilities: members of teams explicitly scoped to affected buildings.
    - IT: members of teams explicitly scoped to affected services.
    - Academic Ops: members of teams scoped to affected sections/departments;
      no role-wide fallback.
    - Faculty: instructors linked via 'taught_by' (pack) or 'teaches' (legacy).
    - Students: enrolled_in affected sections.

    IMPORTANT: empty audience never means allow-all.  When responsibility
    cannot be resolved, the role's audience is empty.  Callers must treat an
    empty result as unresolved scope, not as permission to proceed.

    Returns:
        {
            student:      list[str],   # person IDs
            faculty:      list[str],
            facilities:   list[str],
            it:           list[str],
            academic_ops: list[str],
        }
    """
    import json

    audience: dict[str, set[str]] = {
        "student": set(),
        "faculty": set(),
        "facilities": set(),
        "it": set(),
        "academic_ops": set(),
    }

    try:
        entity_refs = json.loads(canonical_event.entity_refs_json or "[]")
    except (json.JSONDecodeError, TypeError):
        entity_refs = []

    for ref in entity_refs:
        etype = ref.get("type", "")
        eid = ref.get("id", "")
        if not etype or not eid:
            continue

        impact = impact_of(db, etype, eid)

        # Students: enrolled in affected sections
        for sec_id in impact["sections"]:
            enrolled_links = db.query(EntityLink).filter(
                EntityLink.to_type == "section",
                EntityLink.to_id == sec_id,
                EntityLink.rel == "enrolled_in",
            ).all()
            for link in enrolled_links:
                audience["student"].add(link.from_id)

            # Faculty: taught_by (pack loader: section→taught_by→person)
            # or teaches (legacy: person→teaches→section)
            taught_by_links = db.query(EntityLink).filter(
                EntityLink.from_type == "section",
                EntityLink.from_id == sec_id,
                EntityLink.rel == "taught_by",
            ).all()
            for link in taught_by_links:
                audience["faculty"].add(link.to_id)

            teaches_links = db.query(EntityLink).filter(
                EntityLink.to_type == "section",
                EntityLink.to_id == sec_id,
                EntityLink.rel == "teaches",
            ).all()
            for link in teaches_links:
                audience["faculty"].add(link.from_id)

        # Facilities: V4-02 — members of teams scoped to affected buildings only.
        # No role-wide fallback. Audience is empty when no scoped_to link exists.
        for bldg_id in impact["buildings"]:
            for pid in _team_members_scoped_to(db, "building", bldg_id):
                audience["facilities"].add(pid)

        # IT: V4-02 — members of teams scoped to affected services only.
        # No role-wide fallback.
        for svc_id in impact["services"]:
            for pid in _team_members_scoped_to(db, "service", svc_id):
                audience["it"].add(pid)

        # Academic Ops: members of teams scoped to affected sections or departments.
        # No role-wide fallback. Audience is empty when no scoped_to link exists.
        if impact["sections"] or impact["buildings"]:
            for sec_id in impact["sections"]:
                for pid in _team_members_scoped_to(db, "section", sec_id):
                    audience["academic_ops"].add(pid)
            for bldg_id in impact["buildings"]:
                for pid in _team_members_scoped_to(db, "department", bldg_id):
                    audience["academic_ops"].add(pid)

    # No entity-ref type fallback: if entity_refs is empty, all audience sets
    # are empty.  This is intentional — the caller must handle unresolved scope.

    return {role: sorted(ids) for role, ids in audience.items()}

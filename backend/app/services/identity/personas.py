"""Seed the demo personas (people, teams, memberships) into the tenant DB.

This runs at startup and is idempotent — re-running it changes nothing if the
rows already exist.

U1: creates the six non-student personas as Person rows.  student_alex already
exists as UserProfile (V2 demo_user_id); the others are placeholders until the
full pack loader arrives in U2.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import Person, Team, TeamMembership, RoleAssignment


# ── Demo personas ──────────────────────────────────────────────────────────────

_PERSONAS = [
    {"id": "student_alex",      "display_name": "Alex (Student)",            "role": "student"},
    {"id": "student_blake",     "display_name": "Blake (Student)",           "role": "student"},
    {"id": "student_casey",     "display_name": "Casey (Student)",           "role": "student"},
    {"id": "student_dana",      "display_name": "Dana (Student)",            "role": "student"},
    {"id": "faculty_jordan",    "display_name": "Jordan (Faculty)",          "role": "faculty"},
    {"id": "faculty_sam",       "display_name": "Sam (Faculty)",             "role": "faculty"},
    {"id": "facilities_morgan", "display_name": "Morgan (Facilities)",       "role": "facilities"},
    {"id": "it_casey",          "display_name": "Casey (IT)",                "role": "it"},
    {"id": "acadops_taylor",    "display_name": "Taylor (Academic Ops)",     "role": "academic_ops"},
    {"id": "org_riley",         "display_name": "Riley (Org Organizer)",     "role": "org_organizer"},
]

_TEAMS = [
    {"id": "team-facilities",   "name": "Facilities",          "role_type": "facilities",   "scope_type": "campus"},
    {"id": "team-it",           "name": "IT Service Desk",     "role_type": "it",           "scope_type": "campus"},
    {"id": "team-acadops",      "name": "Academic Operations", "role_type": "academic_ops", "scope_type": "campus"},
]

_MEMBERSHIPS = [
    {"person_id": "facilities_morgan", "team_id": "team-facilities", "is_lead": True},
    {"person_id": "it_casey",          "team_id": "team-it",          "is_lead": True},
    {"person_id": "acadops_taylor",    "team_id": "team-acadops",     "is_lead": True},
]

_ROLE_ASSIGNMENTS = [
    # Students get campus-wide student role
    {"person_id": "student_alex",      "role": "student",       "scope_type": "campus"},
    {"person_id": "student_blake",     "role": "student",       "scope_type": "campus"},
    {"person_id": "student_casey",     "role": "student",       "scope_type": "campus"},
    {"person_id": "student_dana",      "role": "student",       "scope_type": "campus"},
    # Faculty
    {"person_id": "faculty_jordan",    "role": "faculty",       "scope_type": "campus"},
    {"person_id": "faculty_sam",       "role": "faculty",       "scope_type": "campus"},
    # Staff
    {"person_id": "facilities_morgan", "role": "facilities",    "scope_type": "campus"},
    {"person_id": "it_casey",          "role": "it",            "scope_type": "campus"},
    {"person_id": "acadops_taylor",    "role": "academic_ops",  "scope_type": "campus"},
    {"person_id": "org_riley",         "role": "org_organizer", "scope_type": "campus"},
]


def seed_personas(db: Session) -> None:
    """Idempotently seed persona rows."""
    for p in _PERSONAS:
        if db.get(Person, p["id"]) is None:
            db.add(Person(**p, data_origin="synthetic"))

    for t in _TEAMS:
        if db.get(Team, t["id"]) is None:
            db.add(Team(**t, data_origin="synthetic"))

    db.flush()

    existing_memberships = {
        (m.person_id, m.team_id)
        for m in db.query(TeamMembership).all()
    }
    for m in _MEMBERSHIPS:
        key = (m["person_id"], m["team_id"])
        if key not in existing_memberships:
            db.add(TeamMembership(**m))

    existing_roles = {
        (r.person_id, r.role, r.scope_type)
        for r in db.query(RoleAssignment).all()
    }
    for r in _ROLE_ASSIGNMENTS:
        key = (r["person_id"], r["role"], r.get("scope_type"))
        if key not in existing_roles:
            db.add(RoleAssignment(**r))

    db.commit()

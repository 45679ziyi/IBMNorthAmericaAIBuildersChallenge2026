"""Identity endpoints — U1.

GET  /identity/personas            → list of demo personas
GET  /identity/me                  → current actor's identity + capabilities + nav items
GET  /identity/effective-permissions → list of allowed actions for this actor
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.core.tenancy import ActorContext, resolve_actor, KNOWN_PERSONAS
from app.services.authz import authorize, POLICY_TABLE

router = APIRouter(prefix="/identity", tags=["identity"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class PersonaInfo(BaseModel):
    id: str
    display_name: str
    role: str
    has_personal_data: bool


class NavItem(BaseModel):
    key: str
    label: str
    path: str


class IdentityMe(BaseModel):
    actor_id: str
    role: str
    display_name: str
    tenant: str
    has_personal_data: bool
    capabilities: list[str]
    nav: list[NavItem]
    auth_mode: str = "demo-persona"
    disclaimer: str = "DEMO PERSONA, NOT AUTHENTICATION"


class PermissionEntry(BaseModel):
    action: str
    allowed: bool
    reason_code: str


# ── Persona display names (V1 statics; overridden by pack loader in U2) ────────

_DISPLAY_NAMES: dict[str, str] = {
    "student_alex":      "Alex (Student)",
    "student_blake":     "Blake (Student)",
    "student_casey":     "Casey (Student)",
    "student_dana":      "Dana (Student)",
    "faculty_jordan":    "Jordan (Faculty)",
    "faculty_sam":       "Sam (Faculty)",
    "facilities_morgan": "Morgan (Facilities)",
    "it_casey":          "Casey (IT Service Desk)",
    "acadops_taylor":    "Taylor (Academic Operations)",
    "org_riley":         "Riley (Student Org)",
}

_PERSONAL_DATA_ROLES = {"student"}

# Nav items per role — U5: role-aware navigation from GET /identity/me
_ROLE_NAV: dict[str, list[NavItem]] = {
    "student": [
        NavItem(key="today",     label="Today",    path="/"),
        NavItem(key="planner",   label="Plan",     path="/planner"),
        NavItem(key="tasks",     label="Tasks",    path="/tasks"),
        NavItem(key="campus",    label="Campus",   path="/campus"),
        NavItem(key="assistant", label="Ask",      path="/assistant"),
        NavItem(key="inbox",     label="Inbox",    path="/inbox"),
    ],
    "faculty": [
        NavItem(key="today",     label="Today",    path="/"),
        NavItem(key="faculty",   label="Courses",  path="/faculty"),
        NavItem(key="campus",    label="Campus",   path="/campus"),
        NavItem(key="assistant", label="Ask",      path="/assistant"),
        NavItem(key="inbox",     label="Inbox",    path="/inbox"),
    ],
    "facilities": [
        NavItem(key="today",     label="Today",    path="/"),
        NavItem(key="facilities", label="Facilities", path="/facilities"),
        NavItem(key="campus",    label="Campus",   path="/campus"),
        NavItem(key="assistant", label="Ask",      path="/assistant"),
        NavItem(key="inbox",     label="Inbox",    path="/inbox"),
    ],
    "it": [
        NavItem(key="today",     label="Today",    path="/"),
        NavItem(key="it",        label="IT Ops",   path="/it"),
        NavItem(key="campus",    label="Campus",   path="/campus"),
        NavItem(key="assistant", label="Ask",      path="/assistant"),
        NavItem(key="inbox",     label="Inbox",    path="/inbox"),
    ],
    "academic_ops": [
        NavItem(key="today",     label="Today",    path="/"),
        NavItem(key="acadops",   label="Acad Ops", path="/acadops"),
        NavItem(key="campus",    label="Campus",   path="/campus"),
        NavItem(key="assistant", label="Ask",      path="/assistant"),
        NavItem(key="inbox",     label="Inbox",    path="/inbox"),
        NavItem(key="trust",     label="Quality",  path="/trust"),
    ],
    "org_organizer": [
        NavItem(key="today",     label="Today",    path="/"),
        NavItem(key="org",       label="Events",   path="/org"),
        NavItem(key="campus",    label="Campus",   path="/campus"),
        NavItem(key="assistant", label="Ask",      path="/assistant"),
        NavItem(key="inbox",     label="Inbox",    path="/inbox"),
    ],
}


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/personas", response_model=list[PersonaInfo])
def list_personas(actor: ActorContext = Depends(resolve_actor)):
    """Return the list of demo personas available in this demo."""
    return [
        PersonaInfo(
            id=pid,
            display_name=_DISPLAY_NAMES.get(pid, pid),
            role=role,
            has_personal_data=(role in _PERSONAL_DATA_ROLES),
        )
        for pid, role in KNOWN_PERSONAS.items()
    ]


@router.get("/me", response_model=IdentityMe)
def get_me(
    actor: ActorContext = Depends(resolve_actor),
    x_demo_tenant: Optional[str] = None,
):
    """Return the current actor's identity, capabilities and navigation."""
    from fastapi import Request
    from starlette.requests import Request as StarletteRequest

    # Build capability list from policy table
    capabilities = [
        rule.action
        for rule in POLICY_TABLE
        if actor.role in rule.allowed and actor.role not in rule.denied
    ]

    nav = _ROLE_NAV.get(actor.role, _ROLE_NAV["student"])

    return IdentityMe(
        actor_id=actor.actor_id,
        role=actor.role,
        display_name=_DISPLAY_NAMES.get(actor.actor_id, actor.actor_id),
        tenant=x_demo_tenant or "sbu_demo",
        has_personal_data=(actor.role in _PERSONAL_DATA_ROLES),
        capabilities=capabilities,
        nav=nav,
    )


@router.get("/effective-permissions", response_model=list[PermissionEntry])
def get_effective_permissions(actor: ActorContext = Depends(resolve_actor)):
    """Return all policy rules evaluated for this actor."""
    results = []
    for rule in POLICY_TABLE:
        d = authorize(actor, rule.action)
        results.append(PermissionEntry(
            action=rule.action,
            allowed=d.allow,
            reason_code=d.reason_code,
        ))
    return results

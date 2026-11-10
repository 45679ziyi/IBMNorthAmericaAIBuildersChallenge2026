"""Authorization service — U1.

authorize(actor, action, resource, purpose) → Decision

Deny by default.  Policy is declared as a list of rules below; each rule has
the minimal information needed to make the decision without querying the DB.

Appendix B of the V3 brief defines the authorization matrix.  This module
implements the part needed for U1 (static role-based policy).  Relationship-
based checks (enrolled_in, teaches, team_scope) are added in U3 when the
entity_links graph is available.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.core.tenancy import ActorContext


# ── Decision ───────────────────────────────────────────────────────────────────

@dataclass
class Decision:
    allow: bool
    reason_code: str
    reason: str
    scope: Optional[str] = None
    redactions: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.allow


# ── Policy table ───────────────────────────────────────────────────────────────
# Each entry: (action_pattern, allowed_roles, deny_roles, reason_code)
#
# action_pattern: exact action string or "resource:*" wildcard.
# allowed_roles:  roles allowed by this rule ([] = no role-based allow).
# deny_roles:     roles explicitly denied (takes precedence).
# reason_code:    machine-readable code returned in 403.
#
# Rules are evaluated in order; first match wins.
# Default: deny with POLICY_DENY.

@dataclass
class PolicyRule:
    action: str                          # exact or "prefix:*"
    allowed: frozenset[str]              # roles allowed
    denied: frozenset[str] = field(default_factory=frozenset)
    reason_code: str = "POLICY_DENY"
    note: str = ""


def _roles(*roles: str) -> frozenset[str]:
    return frozenset(roles)


_ALL_ROLES = _roles(
    "student", "faculty", "facilities", "it", "academic_ops", "org_organizer"
)

# fmt: off
POLICY_TABLE: list[PolicyRule] = [
    # ── Personal data (calendar, tasks, announcements, plan) ─────────────────
    # Only students have personal data rows; others get 403 with an explanation.
    PolicyRule("read:own_calendar",    _roles("student"),                    reason_code="PERSONAL_DATA_STUDENT_ONLY"),
    PolicyRule("write:own_calendar",   _roles("student"),                    reason_code="PERSONAL_DATA_STUDENT_ONLY"),
    PolicyRule("read:own_tasks",       _roles("student"),                    reason_code="PERSONAL_DATA_STUDENT_ONLY"),
    PolicyRule("write:own_tasks",      _roles("student"),                    reason_code="PERSONAL_DATA_STUDENT_ONLY"),
    PolicyRule("read:own_announcements", _roles("student"),                  reason_code="PERSONAL_DATA_STUDENT_ONLY"),
    PolicyRule("read:own_plan",        _roles("student"),                    reason_code="PERSONAL_DATA_STUDENT_ONLY"),
    PolicyRule("write:own_plan",       _roles("student"),                    reason_code="PERSONAL_DATA_STUDENT_ONLY"),

    # ── Moves / decisions ─────────────────────────────────────────────────────
    PolicyRule("read:moves_student",   _roles("student"),                    reason_code="STUDENT_ONLY"),
    PolicyRule("write:moves_student",  _roles("student"),                    reason_code="STUDENT_ONLY"),
    PolicyRule("read:moves_staff",     _roles("facilities", "it", "academic_ops", "faculty"), reason_code="STAFF_ONLY"),
    PolicyRule("write:moves_staff",    _roles("facilities", "it", "academic_ops"),            reason_code="STAFF_ONLY"),

    # ── Sim / scenario controls ───────────────────────────────────────────────
    # Sim is a demo-only meta-feature; all personas can use it.
    PolicyRule("sim:*",                _ALL_ROLES,                           reason_code="DEMO_ONLY"),

    # ── Ask / retrieval ───────────────────────────────────────────────────────
    PolicyRule("ask:personal",         _roles("student"),                    reason_code="PERSONAL_SCOPE_STUDENT_ONLY"),
    PolicyRule("ask:course",           _roles("student", "faculty"),         reason_code="COURSE_SCOPE_DENIED"),
    PolicyRule("ask:campus",           _ALL_ROLES,                           reason_code="CAMPUS_SCOPE_DENIED"),
    PolicyRule("ask:operations",       _roles("facilities", "it", "academic_ops"), reason_code="OPS_SCOPE_DENIED"),
    PolicyRule("ask:service_desk",     _roles("facilities", "it"),           reason_code="SERVICE_DESK_SCOPE_DENIED"),

    # ── Incident / work items ─────────────────────────────────────────────────
    PolicyRule("read:incident",        _ALL_ROLES,                           reason_code="INCIDENT_ACCESS_DENIED"),
    PolicyRule("write:incident",       _roles("facilities", "it", "academic_ops"), reason_code="INCIDENT_WRITE_DENIED"),
    PolicyRule("triage:incident",      _roles("facilities", "it"),           reason_code="TRIAGE_ROLE_DENIED"),
    PolicyRule("resolve:incident",     _roles("facilities", "it"),           reason_code="RESOLVE_ROLE_DENIED"),

    # ── Room reassignment ─────────────────────────────────────────────────────
    # Facilities proposes; academic_ops approves.  Facilities CANNOT approve.
    PolicyRule("propose:room_change",  _roles("facilities"),                 reason_code="FACILITIES_ONLY"),
    PolicyRule("approve:room_change",  _roles("academic_ops"),
               denied=_roles("facilities"),                                  reason_code="ACADOPS_ONLY"),
    PolicyRule("reject:room_change",   _roles("academic_ops"),
               denied=_roles("facilities"),                                  reason_code="ACADOPS_ONLY"),

    # ── Course updates ────────────────────────────────────────────────────────
    PolicyRule("draft:course_update",  _roles("faculty"),                    reason_code="FACULTY_ONLY"),
    PolicyRule("approve:course_update", _roles("faculty"),                   reason_code="FACULTY_ONLY"),

    # ── Service requests ─────────────────────────────────────────────────────
    PolicyRule("submit:service_request", _ALL_ROLES,                         reason_code="SERVICE_REQUEST_DENIED"),
    PolicyRule("read:service_request_own", _ALL_ROLES,                       reason_code="OWN_ONLY"),
    PolicyRule("read:service_request_team", _roles("facilities", "it", "academic_ops"), reason_code="TEAM_SCOPE_DENIED"),

    # ── Identity ─────────────────────────────────────────────────────────────
    PolicyRule("read:identity_personas", _ALL_ROLES,                         reason_code="IDENTITY_DENIED"),
    PolicyRule("read:identity_me",       _ALL_ROLES,                         reason_code="IDENTITY_DENIED"),

    # ── Admin ─────────────────────────────────────────────────────────────────
    PolicyRule("admin:*",             frozenset(),                            reason_code="ADMIN_ONLY"),
]
# fmt: on

# Pre-index by action for O(1) lookup on exact matches.
_EXACT: dict[str, PolicyRule] = {}
_PREFIX: list[tuple[str, PolicyRule]] = []

for _rule in POLICY_TABLE:
    if _rule.action.endswith(":*"):
        _PREFIX.append((_rule.action[:-2], _rule))
    else:
        _EXACT[_rule.action] = _rule


def _find_rule(action: str) -> Optional[PolicyRule]:
    if action in _EXACT:
        return _EXACT[action]
    for prefix, rule in _PREFIX:
        if action.startswith(prefix):
            return rule
    return None


# ── authorize ──────────────────────────────────────────────────────────────────

def authorize(
    actor: ActorContext,
    action: str,
    resource: Optional[str] = None,
    purpose: Optional[str] = None,
) -> Decision:
    """Evaluate whether actor may perform action on resource.

    Returns a Decision with allow=True/False, reason_code, and a human sentence.
    """
    rule = _find_rule(action)
    if rule is None:
        return Decision(
            allow=False,
            reason_code="NO_POLICY",
            reason=(
                f"No policy rule found for action '{action}'. "
                "This action is not authorized by default."
            ),
        )

    # Explicit deny takes precedence
    if actor.role in rule.denied:
        return Decision(
            allow=False,
            reason_code=rule.reason_code,
            reason=_deny_sentence(actor, action, rule),
        )

    if actor.role in rule.allowed:
        return Decision(
            allow=True,
            reason_code="ALLOWED",
            reason=f"Role '{actor.role}' may perform '{action}'.",
        )

    return Decision(
        allow=False,
        reason_code=rule.reason_code,
        reason=_deny_sentence(actor, action, rule),
    )


def _deny_sentence(actor: ActorContext, action: str, rule: PolicyRule) -> str:
    allowed = sorted(rule.allowed)
    if not allowed:
        return (
            f"The action '{action}' is not permitted for any role in this context."
        )
    if len(allowed) == 1:
        return (
            f"Only {allowed[0]} may perform '{action}'. "
            f"You are acting as {actor.role} ({actor.actor_id})."
        )
    return (
        f"Only {', '.join(allowed[:-1])} or {allowed[-1]} may perform '{action}'. "
        f"You are acting as {actor.role} ({actor.actor_id})."
    )


# ── Small-count suppression ────────────────────────────────────────────────────

DEFAULT_MIN_CELL_SIZE = 5


def suppress_small_count(count: int, min_cell_size: int = DEFAULT_MIN_CELL_SIZE) -> str | int:
    """Return count if >= min_cell_size, else a suppression string."""
    if count < min_cell_size:
        return f"fewer than {min_cell_size}"
    return count


# ── project ───────────────────────────────────────────────────────────────────

def project(data: dict, actor: ActorContext, resource_type: str) -> dict:
    """Return a role-specific projection of data.

    For impact counts: facilities/IT see only aggregate counts (no names).
    Students see only their own entries.
    Instructors see section rosters for their own sections.
    """
    # Simple projection rules; graph-based rules added in U3.
    if resource_type == "impact_counts":
        # All staff roles see counts; suppression applied by caller.
        return data

    if resource_type == "person_name":
        # Only the person themselves and authorized owners may see names.
        target_id = data.get("person_id")
        if target_id == actor.actor_id:
            return data
        # Redact name; return only role and relationship hint.
        return {k: v for k, v in data.items() if k not in ("name", "email", "display_name")}

    return data

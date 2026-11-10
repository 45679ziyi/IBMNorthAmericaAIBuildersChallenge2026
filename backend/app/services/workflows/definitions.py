"""Workflow definitions — U3.

Six workflow types:
  - course_update
  - incident_response
  - room_reassignment
  - service_disruption
  - service_request
  - event_change

Each workflow is represented as a dict with:
  initial_status: str
  transitions: list[TransitionDef]

Each TransitionDef has:
  from_status: str
  to_status: str
  action: str          # action name used in API
  allowed_roles: list[str]
  denied_roles: list[str]
  required_fields: list[str]   # fields required in payload for this transition
  effects: list[str]           # side effects to apply
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TransitionDef:
    from_status: str
    to_status: str
    action: str
    allowed_roles: list[str]
    denied_roles: list[str] = field(default_factory=list)
    required_fields: list[str] = field(default_factory=list)
    effects: list[str] = field(default_factory=list)


@dataclass
class WorkflowDef:
    name: str
    initial_status: str
    transitions: list[TransitionDef]

    def get_transition(self, from_status: str, action: str) -> TransitionDef | None:
        for t in self.transitions:
            if t.from_status == from_status and t.action == action:
                return t
        return None

    def valid_actions_from(self, status: str) -> list[str]:
        return [t.action for t in self.transitions if t.from_status == status]

    def is_terminal(self, status: str) -> bool:
        return not any(t.from_status == status for t in self.transitions)


# ── course_update ─────────────────────────────────────────────────────────────
# drafted → previewed → approved → published
#                     ↘ rejected (from previewed)

COURSE_UPDATE = WorkflowDef(
    name="course_update",
    initial_status="drafted",
    transitions=[
        TransitionDef(
            from_status="drafted",
            to_status="previewed",
            action="submit_for_preview",
            allowed_roles=["faculty"],
            effects=["notify_academic_ops"],
        ),
        TransitionDef(
            from_status="previewed",
            to_status="approved",
            action="approve",
            allowed_roles=["faculty", "academic_ops"],
            required_fields=["approval_note"],
            effects=["notify_students", "audit"],
        ),
        TransitionDef(
            from_status="previewed",
            to_status="rejected",
            action="reject",
            allowed_roles=["faculty", "academic_ops"],
            required_fields=["rejection_reason"],
            effects=["notify_author", "audit"],
        ),
        TransitionDef(
            from_status="approved",
            to_status="published",
            action="publish",
            allowed_roles=["faculty", "academic_ops"],
            effects=["notify_students", "audit"],
        ),
    ],
)


# ── incident_response ─────────────────────────────────────────────────────────
# reported → triage → impact_assessed → mitigated → resolved → closed

INCIDENT_RESPONSE = WorkflowDef(
    name="incident_response",
    initial_status="reported",
    transitions=[
        TransitionDef(
            from_status="reported",
            to_status="triage",
            action="start_triage",
            allowed_roles=["facilities", "it"],
            effects=["audit"],
        ),
        TransitionDef(
            from_status="triage",
            to_status="impact_assessed",
            action="assess_impact",
            allowed_roles=["facilities", "it"],
            required_fields=["impact_summary"],
            effects=["notify_academic_ops", "audit"],
        ),
        TransitionDef(
            from_status="impact_assessed",
            to_status="mitigated",
            action="mitigate",
            allowed_roles=["facilities", "it"],
            required_fields=["mitigation_action"],
            effects=["notify_affected", "audit"],
        ),
        TransitionDef(
            from_status="mitigated",
            to_status="resolved",
            action="resolve",
            allowed_roles=["facilities", "it"],
            effects=["notify_affected", "audit"],
        ),
        TransitionDef(
            from_status="resolved",
            to_status="closed",
            action="close",
            allowed_roles=["facilities", "it", "academic_ops"],
            effects=["audit"],
        ),
    ],
)


# ── room_reassignment ─────────────────────────────────────────────────────────
# proposed → awaiting_approval → approved → applied
#                              ↘ rejected

ROOM_REASSIGNMENT = WorkflowDef(
    name="room_reassignment",
    initial_status="proposed",
    transitions=[
        TransitionDef(
            from_status="proposed",
            to_status="awaiting_approval",
            action="submit",
            allowed_roles=["facilities"],
            required_fields=["new_room_id", "reason"],
            effects=["notify_academic_ops", "audit"],
        ),
        TransitionDef(
            from_status="awaiting_approval",
            to_status="approved",
            action="approve",
            allowed_roles=["academic_ops"],
            denied_roles=["facilities"],
            required_fields=["approval_note"],
            effects=["notify_facilities", "notify_faculty", "notify_students", "audit"],
        ),
        TransitionDef(
            from_status="awaiting_approval",
            to_status="rejected",
            action="reject",
            allowed_roles=["academic_ops"],
            denied_roles=["facilities"],
            required_fields=["rejection_reason"],
            effects=["notify_facilities", "audit"],
        ),
        TransitionDef(
            from_status="approved",
            to_status="applied",
            action="apply",
            allowed_roles=["facilities", "academic_ops"],
            effects=["update_room_assignment", "notify_students", "audit"],
        ),
    ],
)


# ── service_disruption ───────────────────────────────────────────────────────
# reported → triage → in_progress → mitigated → resolved → closed
# (+ correlate: allows joining a second report to an existing disruption)

SERVICE_DISRUPTION = WorkflowDef(
    name="service_disruption",
    initial_status="reported",
    transitions=[
        TransitionDef(
            from_status="reported",
            to_status="triage",
            action="start_triage",
            allowed_roles=["it", "facilities"],
            effects=["audit"],
        ),
        TransitionDef(
            from_status="triage",
            to_status="in_progress",
            action="start_work",
            allowed_roles=["it", "facilities"],
            required_fields=["assigned_team"],
            effects=["notify_affected", "audit"],
        ),
        TransitionDef(
            from_status="in_progress",
            to_status="mitigated",
            action="mitigate",
            allowed_roles=["it", "facilities"],
            required_fields=["mitigation_action"],
            effects=["notify_affected", "audit"],
        ),
        TransitionDef(
            from_status="mitigated",
            to_status="resolved",
            action="resolve",
            allowed_roles=["it", "facilities"],
            effects=["notify_affected", "audit"],
        ),
        TransitionDef(
            from_status="resolved",
            to_status="closed",
            action="close",
            allowed_roles=["it", "facilities", "academic_ops"],
            effects=["audit"],
        ),
    ],
)


# ── service_request ───────────────────────────────────────────────────────────
# submitted → triaged → in_progress → resolved → closed

SERVICE_REQUEST = WorkflowDef(
    name="service_request",
    initial_status="submitted",
    transitions=[
        TransitionDef(
            from_status="submitted",
            to_status="triaged",
            action="triage",
            allowed_roles=["facilities", "it", "academic_ops"],
            required_fields=["priority"],
            effects=["audit"],
        ),
        TransitionDef(
            from_status="triaged",
            to_status="in_progress",
            action="start_work",
            allowed_roles=["facilities", "it", "academic_ops"],
            required_fields=["assigned_team"],
            effects=["notify_requester", "audit"],
        ),
        TransitionDef(
            from_status="in_progress",
            to_status="resolved",
            action="resolve",
            allowed_roles=["facilities", "it", "academic_ops"],
            required_fields=["resolution_note"],
            effects=["notify_requester", "audit"],
        ),
        TransitionDef(
            from_status="resolved",
            to_status="closed",
            action="close",
            allowed_roles=["facilities", "it", "academic_ops"],
            effects=["audit"],
        ),
    ],
)


# ── event_change ──────────────────────────────────────────────────────────────
# proposed → conflict_checked → approved → published

EVENT_CHANGE = WorkflowDef(
    name="event_change",
    initial_status="proposed",
    transitions=[
        TransitionDef(
            from_status="proposed",
            to_status="conflict_checked",
            action="check_conflicts",
            allowed_roles=["academic_ops", "faculty"],
            effects=["run_conflict_check", "audit"],
        ),
        TransitionDef(
            from_status="conflict_checked",
            to_status="approved",
            action="approve",
            allowed_roles=["academic_ops"],
            required_fields=["approval_note"],
            effects=["notify_affected", "audit"],
        ),
        TransitionDef(
            from_status="conflict_checked",
            to_status="proposed",
            action="reject",
            allowed_roles=["academic_ops"],
            required_fields=["rejection_reason"],
            effects=["notify_author", "audit"],
        ),
        TransitionDef(
            from_status="approved",
            to_status="published",
            action="publish",
            allowed_roles=["academic_ops"],
            effects=["notify_students", "notify_faculty", "audit"],
        ),
    ],
)


# ── Registry ──────────────────────────────────────────────────────────────────

WORKFLOW_REGISTRY: dict[str, WorkflowDef] = {
    "course_update": COURSE_UPDATE,
    "incident_response": INCIDENT_RESPONSE,
    "room_reassignment": ROOM_REASSIGNMENT,
    "service_disruption": SERVICE_DISRUPTION,
    "service_request": SERVICE_REQUEST,
    "event_change": EVENT_CHANGE,
}

# Map canonical event type prefixes to workflow type
EVENT_TYPE_TO_WORKFLOW: dict[str, str] = {
    "incident": "incident_response",
    "service_disruption": "service_disruption",
    "service_request": "service_request",
    "section_update": "course_update",
    "course_update": "course_update",
    "room_change": "room_reassignment",
    "event_change": "event_change",
}


def workflow_for_event_type(event_type: str) -> str | None:
    """Return the workflow type for a given canonical event type prefix."""
    for prefix, wf_type in EVENT_TYPE_TO_WORKFLOW.items():
        if event_type == prefix or event_type.startswith(prefix + "."):
            return wf_type
    return None

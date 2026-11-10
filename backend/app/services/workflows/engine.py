"""Workflow engine — U3.

WorkflowEngine.advance() validates a transition request and applies it,
writing an audit WorkItemTransition row.

Raises:
  409 Conflict — illegal transition (wrong state, wrong role, version mismatch)
  403 Forbidden — role not allowed for this action
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.core.tenancy import ActorContext
from app.models.models import WorkItem, WorkItemTransition
from app.services.workflows.definitions import WORKFLOW_REGISTRY, WorkflowDef, TransitionDef


@dataclass
class TransitionRequest:
    action: str
    payload: dict = None           # additional fields for this transition
    rationale: Optional[str] = None
    expected_version: Optional[int] = None  # for optimistic locking
    actor_mode: str = "human"      # human | autopilot

    def __post_init__(self):
        if self.payload is None:
            self.payload = {}


class WorkflowEngine:
    """Stateless engine — all state lives in the DB."""

    def advance(
        self,
        db: Session,
        work_item: WorkItem,
        transition: TransitionRequest,
        actor: ActorContext,
    ) -> WorkItem:
        """Validate and apply a workflow transition.

        Checks:
          1. Workflow type is recognized.
          2. There exists a transition from current_status with the given action.
          3. Actor's role is allowed (and not explicitly denied).
          4. Required fields are present in the transition payload.
          5. Version matches expected_version (optimistic lock).

        On success, persists the new status and writes a WorkItemTransition audit row.
        On failure, raises HTTPException 409 or 403.
        """
        wf: Optional[WorkflowDef] = WORKFLOW_REGISTRY.get(work_item.workflow_type)
        if wf is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "reason_code": "UNKNOWN_WORKFLOW",
                    "message": f"Workflow type '{work_item.workflow_type}' is not defined.",
                },
            )

        tdef: Optional[TransitionDef] = wf.get_transition(work_item.status, transition.action)
        if tdef is None:
            valid = wf.valid_actions_from(work_item.status)
            raise HTTPException(
                status_code=409,
                detail={
                    "reason_code": "ILLEGAL_TRANSITION",
                    "message": (
                        f"Cannot perform action '{transition.action}' "
                        f"from status '{work_item.status}'. "
                        f"Valid actions: {valid}"
                    ),
                    "current_status": work_item.status,
                    "requested_action": transition.action,
                    "valid_actions": valid,
                },
            )

        # Role check: deny first, then allow
        if actor.role in tdef.denied_roles:
            raise HTTPException(
                status_code=403,
                detail={
                    "reason_code": "ROLE_DENIED",
                    "message": (
                        f"Role '{actor.role}' is explicitly denied for action "
                        f"'{transition.action}' on workflow '{work_item.workflow_type}'."
                    ),
                    "actor_role": actor.role,
                    "action": transition.action,
                },
            )

        if actor.role not in tdef.allowed_roles:
            raise HTTPException(
                status_code=403,
                detail={
                    "reason_code": "ROLE_NOT_ALLOWED",
                    "message": (
                        f"Role '{actor.role}' may not perform action '{transition.action}'. "
                        f"Allowed roles: {tdef.allowed_roles}"
                    ),
                    "actor_role": actor.role,
                    "action": transition.action,
                    "allowed_roles": tdef.allowed_roles,
                },
            )

        # Required fields check
        missing = [f for f in tdef.required_fields if f not in transition.payload]
        if missing:
            raise HTTPException(
                status_code=422,
                detail={
                    "reason_code": "MISSING_REQUIRED_FIELDS",
                    "message": f"Missing required fields for action '{transition.action}': {missing}",
                    "missing_fields": missing,
                },
            )

        # Optimistic lock check
        if transition.expected_version is not None:
            if work_item.version != transition.expected_version:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "reason_code": "VERSION_CONFLICT",
                        "message": (
                            f"Work item version conflict: expected {transition.expected_version}, "
                            f"got {work_item.version}."
                        ),
                        "expected_version": transition.expected_version,
                        "current_version": work_item.version,
                    },
                )

        # Apply transition
        from_status = work_item.status
        to_status = tdef.to_status
        now = get_now()

        work_item.status = to_status
        work_item.version = work_item.version + 1
        work_item.updated_at = now

        # Merge payload into work_item payload
        try:
            existing_payload = json.loads(work_item.payload_json or "{}")
        except (json.JSONDecodeError, TypeError):
            existing_payload = {}
        existing_payload.update(transition.payload)
        work_item.payload_json = json.dumps(existing_payload)

        # Write audit record
        wt = WorkItemTransition(
            work_item_id=work_item.id,
            from_status=from_status,
            to_status=to_status,
            actor_id=actor.actor_id,
            actor_role=actor.role,
            actor_mode=transition.actor_mode,
            rationale=transition.rationale,
            effects_json=json.dumps({"effects": tdef.effects}),
            virtual_time=now,
            created_at=now,
        )
        db.add(wt)
        db.flush()

        return work_item


# Module-level singleton
engine = WorkflowEngine()

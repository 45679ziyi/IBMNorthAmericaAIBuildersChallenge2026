"""
AURORA Autonomy Policy (M3)

Manages the demo user's autonomy policy — which action categories can be
executed automatically vs. which require user confirmation.

Default policy (per V2_BRIEF.md Section 5.5):
  "my_calendar_tasks_reminders": "auto"   — can be changed to "ask"
  "attended_plan_changes": "ask"          — can be changed to "auto"
  "simulated_external": "ask"             — LOCKED: cannot be changed to "auto"
  "message_drafts": "ask"                 — LOCKED: cannot be changed to "auto"

A PUT that tries to change a locked category to "auto" raises PolicyLockError.
All policy changes are written to AuditEvent.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.models.models import AuditEvent, AutonomyPolicy

# ─── Constants ────────────────────────────────────────────────────────────────

LOCKED_CATEGORIES = {"simulated_external", "message_drafts"}

DEFAULT_POLICY: dict[str, str] = {
    "my_calendar_tasks_reminders": "auto",
    "attended_plan_changes": "ask",
    "simulated_external": "ask",   # locked
    "message_drafts": "ask",       # locked
}

# Map action type → policy category
ACTION_TO_CATEGORY: dict[str, str] = {
    "create_calendar_block": "my_calendar_tasks_reminders",
    "update_event_location": "my_calendar_tasks_reminders",
    "create_task": "my_calendar_tasks_reminders",
    "add_reminder": "my_calendar_tasks_reminders",
    "book_room": "simulated_external",
    "request_room_change": "simulated_external",
    "draft_message": "message_drafts",
}


# ─── Exception ────────────────────────────────────────────────────────────────

class PolicyLockError(ValueError):
    """Raised when a PUT attempts to set a locked category to 'auto'."""


# ─── Public API ───────────────────────────────────────────────────────────────

def get_policy(db: Session) -> dict[str, str]:
    """
    Return the current policy dict for the demo user.
    Merges the stored row (if any) over the defaults so that new categories
    always appear even if the stored JSON is stale.
    """
    row = _get_or_create_row(db)
    try:
        stored = json.loads(row.policy_json) if row.policy_json else {}
    except (json.JSONDecodeError, TypeError):
        stored = {}

    # Merge: defaults first, then stored overrides
    policy = dict(DEFAULT_POLICY)
    for k, v in stored.items():
        if k in policy:
            policy[k] = v

    # Always enforce locks
    for cat in LOCKED_CATEGORIES:
        policy[cat] = "ask"

    return policy


def set_policy(db: Session, updates: dict[str, str]) -> dict[str, str]:
    """
    Apply `updates` to the current policy.

    Raises:
        PolicyLockError: if any key in `updates` is a locked category being
                         set to 'auto'.

    Returns:
        The full updated policy dict.
    """
    # Validate first — fail fast before touching the DB
    for category, value in updates.items():
        if category in LOCKED_CATEGORIES and value == "auto":
            raise PolicyLockError(
                f"Category '{category}' is locked and cannot be set to 'auto'. "
                "See docs/V2_BRIEF.md Section 5.5."
            )
        if value not in ("auto", "ask"):
            raise ValueError(
                f"Invalid policy value '{value}'. Must be 'auto' or 'ask'."
            )

    current = get_policy(db)
    for category, value in updates.items():
        if category in current:
            current[category] = value
        # Unknown categories are silently ignored (forward-compat)

    # Always re-enforce locks
    for cat in LOCKED_CATEGORIES:
        current[cat] = "ask"

    # Persist
    row = _get_or_create_row(db)
    row.policy_json = json.dumps(current)

    now = get_now()
    now_naive = now.replace(tzinfo=None) if now.tzinfo else now

    audit = AuditEvent(
        id=str(uuid.uuid4()),
        user_id=None,
        action="set_autonomy_policy",
        resource_type="autonomy_policy",
        resource_id="1",
        result="ok",
        created_at_utc=now_naive,
    )
    db.add(audit)
    db.commit()

    return current


def get_category_for_action(action_type: str) -> str | None:
    """Return the policy category for a given action type, or None if unknown."""
    return ACTION_TO_CATEGORY.get(action_type)


def resolve_action_policy(db: Session, action_type: str) -> str:
    """
    Return 'auto' or 'ask' for a given action type based on the current policy.
    Unknown action types default to 'ask' (safe default).
    """
    category = get_category_for_action(action_type)
    if category is None:
        return "ask"
    policy = get_policy(db)
    return policy.get(category, "ask")


# ─── Internal ─────────────────────────────────────────────────────────────────

def _get_or_create_row(db: Session) -> AutonomyPolicy:
    """Return the singleton AutonomyPolicy row, creating it if absent."""
    row = db.get(AutonomyPolicy, 1)
    if row is None:
        row = AutonomyPolicy(id=1, policy_json=json.dumps(DEFAULT_POLICY))
        db.add(row)
        db.flush()
    return row

"""
AURORA Campus Intelligence Engine — M3

evaluate() runs all detectors, reconciles with stored moves, and returns
current (non-expired) moves.

M3 additions:
- Auto-executes moves whose policy is "auto" AND all action categories resolve
  to "auto" in the autonomy policy.
- Fires reminders whose at_utc <= now and fired=False.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime

import pytz
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.models.models import Move, Reminder
from app.services.campus.detectors.base import MoveSpec
from app.services.campus.world import World, build_world

_log = logging.getLogger(__name__)

_CAMPUS_TZ = pytz.timezone("America/New_York")

# All detector modules (order is deterministic)
from app.services.campus.detectors import (
    deadline_risk,
    change_impact,
    ingestion,
    disruption,
    conflict,
    group_opportunity,
    ops_impact,
)

_DETECTORS = [
    deadline_risk,
    change_impact,
    ingestion,
    disruption,
    conflict,
    group_opportunity,
    ops_impact,
]


def evaluate(db: Session, now: datetime) -> list[Move]:
    """
    Run all detectors against the current world snapshot. Reconcile with stored
    moves. Return all current (non-expired, non-dismissed) moves.

    Reconciliation rules:
    - New key → create Move
    - Existing key + fingerprint changed → update Move (content changed)
    - Existing key + dismissed + same fingerprint → skip (keep dismissed)
    - Existing key + dismissed + fingerprint changed → re-propose
    - Condition disappeared → mark status="expired"

    M3 additions:
    - After creating/updating a move with policy=="auto", check autonomy policy.
      If ALL actions resolve to "auto": execute them, set status="auto_applied".
      If any action is locked (simulated_external, message_drafts): set policy
      to "ask" on the move (do not auto-execute).
    - Fire reminders whose at_utc <= now and fired=False.
    """
    world = build_world(db)
    if world is None:
        return []

    # Run all detectors
    specs: list[MoveSpec] = []
    for detector in _DETECTORS:
        try:
            new_specs = detector.detect(world, now)
            specs.extend(new_specs)
        except Exception as exc:
            _log.warning(
                "Detector %s raised %s: %s",
                detector.__name__, type(exc).__name__, exc,
            )

    scenario_id = world.scenario.get("id")

    # Load existing moves for this scenario
    existing: dict[str, Move] = {
        m.key: m
        for m in db.query(Move).filter(Move.scenario_id == scenario_id).all()
    }

    live_keys: set[str] = set()
    # Collect moves that are newly proposed this cycle and eligible for auto
    auto_candidates: list[Move] = []

    for spec in specs:
        fp = _fingerprint(spec)
        live_keys.add(spec.key)

        if spec.key in existing:
            move = existing[spec.key]
            if move.status == "dismissed" and move.fingerprint == fp:
                # Same content, still dismissed — don't re-propose
                continue
            # Content changed or not dismissed: update
            move.kind = spec.kind
            move.audience = spec.audience
            move.policy = spec.policy
            move.urgency = spec.urgency
            move.impact = spec.impact
            move.title = spec.title
            move.summary = spec.summary
            move.why = json.dumps(spec.why)
            move.actions = json.dumps(spec.actions)
            move.fingerprint = fp
            move.updated_at = now
            if move.fingerprint != fp or move.status in ("expired",):
                move.status = "proposed"
                if spec.policy == "auto":
                    auto_candidates.append(move)
        else:
            # Create new move
            move = Move(
                key=spec.key,
                kind=spec.kind,
                audience=spec.audience,
                status="proposed",
                policy=spec.policy,
                urgency=spec.urgency,
                impact=spec.impact,
                title=spec.title,
                summary=spec.summary,
                why=json.dumps(spec.why),
                actions=json.dumps(spec.actions),
                fingerprint=fp,
                scenario_id=scenario_id,
                created_at=now,
                updated_at=now,
            )
            db.add(move)
            if spec.policy == "auto":
                auto_candidates.append(move)

    # Mark moves whose condition disappeared as "expired"
    for key, move in existing.items():
        if key not in live_keys and move.status == "proposed":
            move.status = "expired"

    db.commit()

    # ── M3: Auto-execute eligible moves ──────────────────────────────────────
    _auto_execute_moves(db, auto_candidates, now)

    # ── M3: Fire due reminders ────────────────────────────────────────────────
    _fire_due_reminders(db, now)

    # Return all non-expired moves
    return (
        db.query(Move)
        .filter(
            Move.scenario_id == scenario_id,
            Move.status != "expired",
        )
        .order_by(Move.created_at)
        .all()
    )


def _auto_execute_moves(db: Session, candidates: list[Move], now: datetime) -> None:
    """
    For each candidate move (policy=="auto", status=="proposed"):
    - Check each action against the autonomy policy category.
    - If any action maps to a locked category → downgrade move.policy to "ask";
      do not execute.
    - If ALL actions resolve to "auto" → execute them; set status="auto_applied".
    """
    if not candidates:
        return

    from app.services.campus.actions import execute_action, SIMULATED_TYPES
    from app.services.campus.autonomy import resolve_action_policy, LOCKED_CATEGORIES, ACTION_TO_CATEGORY

    for move in candidates:
        # Guard: only process proposed moves
        if move.status != "proposed":
            continue

        try:
            actions = json.loads(move.actions) if move.actions else []
        except (json.JSONDecodeError, TypeError):
            actions = []

        if not actions:
            continue

        # Check all action types against policy
        has_locked = False
        all_auto = True
        for action in actions:
            action_type = action.get("type", "")
            category = ACTION_TO_CATEGORY.get(action_type)
            if category in LOCKED_CATEGORIES:
                has_locked = True
                all_auto = False
                break
            policy_val = resolve_action_policy(db, action_type)
            if policy_val != "auto":
                all_auto = False

        if has_locked:
            # Downgrade the move policy — never auto-execute locked actions
            move.policy = "ask"
            move.updated_at = now
            db.flush()
            continue

        if not all_auto:
            continue

        # Execute all actions
        try:
            for action in actions:
                execute_action(db, action, move)
            move.status = "auto_applied"
            move.updated_at = now
            db.flush()
        except Exception as exc:
            _log.warning(
                "Auto-execute failed for move %s: %s", move.key, exc
            )
            db.rollback()

    db.commit()


def _fire_due_reminders(db: Session, now: datetime) -> None:
    """Set fired=True on all Reminder rows with at_utc <= now and fired=False."""
    now_naive = now.replace(tzinfo=None) if now.tzinfo else now
    due = (
        db.query(Reminder)
        .filter(Reminder.fired == False, Reminder.at_utc <= now_naive)  # noqa: E712
        .all()
    )
    for reminder in due:
        reminder.fired = True
    if due:
        db.commit()


def _fingerprint(spec: MoveSpec) -> str:
    """Compute first 16 chars of SHA-1 of title + summary + actions."""
    content = spec.title + spec.summary + json.dumps(spec.actions, sort_keys=True)
    return hashlib.sha1(content.encode()).hexdigest()[:16]

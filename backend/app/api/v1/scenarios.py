"""Scenarios API — V4-05.

Routes:
  POST /scenarios              → create and run a classroom outage scenario
  GET  /scenarios/{id}         → get a scenario run result
  GET  /scenarios/{id}/compare → compare up to 3 scenario runs side by side
  POST /scenarios/{id}/promote → promote a scenario option (authorized human only)

Rules:
  - Scenario runs NEVER mutate canonical events or work items.
  - Promotion is a separate authorized operation with rationale and audit.
  - Promotion rechecks hard constraints before committing.
  - Only academic_ops role may promote (approve) a scenario option.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.core.tenancy import ActorContext, resolve_actor
from app.db.session import get_db
from app.models.models import CanonicalEvent, ScenarioRun
from app.services.authz import authorize
from app.services.scenarios import (
    ClassroomOutageInput,
    ScenarioResult,
    engine as scenario_engine,
)

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class ScenarioCreateBody(BaseModel):
    """Client request to run a classroom outage scenario."""
    canonical_event_id: Optional[str] = None
    affected_room_id: str = Field(..., min_length=1, max_length=128)
    repair_delay_minutes: int = Field(..., ge=0, le=10080)  # max 1 week
    min_capacity: Optional[int] = Field(None, ge=1)
    required_features: list[str] = Field(default_factory=list)
    accepted_kinds: list[str] = Field(default_factory=lambda: ["classroom"])


class PromoteBody(BaseModel):
    selected_option_id: str = Field(..., min_length=1)
    rationale: str = Field(..., min_length=10, max_length=2000)


def _result_to_dict(result: ScenarioResult) -> dict:
    """Convert ScenarioResult dataclass to a JSON-serializable dict."""
    def _conv(obj):
        if hasattr(obj, "__dataclass_fields__"):
            return {k: _conv(v) for k, v in asdict(obj).items()}
        if isinstance(obj, list):
            return [_conv(i) for i in obj]
        if isinstance(obj, dict):
            return {k: _conv(v) for k, v in obj.items()}
        return obj
    return _conv(result)


def _run_to_response(run: ScenarioRun) -> dict:
    try:
        result = json.loads(run.result_json)
    except (json.JSONDecodeError, TypeError):
        result = {}
    try:
        inputs = json.loads(run.inputs_json)
    except (json.JSONDecodeError, TypeError):
        inputs = {}
    return {
        "id": run.id,
        "tenant_id": run.tenant_id,
        "canonical_event_id": run.canonical_event_id,
        "engine_version": run.engine_version,
        "scenario_type": run.scenario_type,
        "status": run.status,
        "inputs": inputs,
        "result": result,
        "result_hash": run.result_hash,
        "promoted_by": run.promoted_by,
        "promoted_at": run.promoted_at.isoformat() if run.promoted_at else None,
        "promoted_option_id": run.promoted_option_id,
        "promotion_rationale": run.promotion_rationale,
        "data_origin": run.data_origin,
        "created_at": run.created_at.isoformat(),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
def create_scenario(
    body: ScenarioCreateBody,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Run a classroom outage what-if scenario.

    The scenario engine is deterministic and independent of any LLM.
    The run does NOT modify any canonical event, work item, or notification.
    Promotion is a separate authorized operation.
    """
    d = authorize(actor, "create:scenario")
    if not d:
        raise HTTPException(
            status_code=403,
            detail={"reason_code": d.reason_code, "message": d.reason},
        )

    # Validate canonical_event_id is in this tenant if provided
    if body.canonical_event_id:
        ce = db.get(CanonicalEvent, body.canonical_event_id)
        if ce is None or ce.tenant_id != actor.tenant_id:
            raise HTTPException(
                status_code=404,
                detail="Canonical event not found in this tenant.",
            )
        context_version = ce.version if hasattr(ce, "version") else None
    else:
        ce = None
        context_version = None

    # Load min_cell_size from tenant config
    from app.models.models import TenantConfig
    cfg = db.query(TenantConfig).first()
    min_cell = cfg.min_cell_size if cfg else 5

    inputs = ClassroomOutageInput(
        affected_room_id=body.affected_room_id,
        repair_delay_minutes=body.repair_delay_minutes,
        min_capacity=body.min_capacity,
        required_features=body.required_features,
        accepted_kinds=body.accepted_kinds,
        context_event_version=context_version,
    )

    scenario_id = "scn_" + uuid.uuid4().hex[:12]
    result = scenario_engine.run(db, inputs, scenario_id, min_cell_size=min_cell)

    # Persist the run record (does NOT affect canonical tables)
    result_dict = _result_to_dict(result)
    run = ScenarioRun(
        id=scenario_id,
        tenant_id=actor.tenant_id,
        canonical_event_id=body.canonical_event_id,
        engine_version=result.engine_version,
        scenario_type=result.scenario_type,
        inputs_json=json.dumps(asdict(inputs)),
        result_json=json.dumps(result_dict),
        result_hash=result.result_hash,
        status="computed",
        data_origin="synthetic_simulation",
        created_by=actor.actor_id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    return _run_to_response(run)


@router.get("/{scenario_id}")
def get_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Get a scenario run result."""
    run = db.get(ScenarioRun, scenario_id)
    if run is None or run.tenant_id != actor.tenant_id:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    return _run_to_response(run)


@router.get("")
def list_scenarios(
    canonical_event_id: Optional[str] = None,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """List scenario runs for this tenant, optionally filtered by canonical event."""
    q = db.query(ScenarioRun).filter(ScenarioRun.tenant_id == actor.tenant_id)
    if canonical_event_id:
        q = q.filter(ScenarioRun.canonical_event_id == canonical_event_id)
    runs = q.order_by(ScenarioRun.created_at.desc()).limit(50).all()
    return [_run_to_response(r) for r in runs]


@router.get("/compare/{id_a}/{id_b}")
def compare_scenarios(
    id_a: str,
    id_b: str,
    id_c: Optional[str] = None,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Compare 2 or 3 scenario runs side by side.

    Returns a structured comparison highlighting shared inputs, changed inputs,
    best candidates from each, and determinism status.
    """
    runs = []
    for sid in [id_a, id_b, id_c]:
        if sid is None:
            continue
        run = db.get(ScenarioRun, sid)
        if run is None or run.tenant_id != actor.tenant_id:
            raise HTTPException(status_code=404, detail=f"Scenario '{sid}' not found.")
        runs.append(run)

    comparison = []
    for run in runs:
        try:
            inputs = json.loads(run.inputs_json)
            result = json.loads(run.result_json)
        except (json.JSONDecodeError, TypeError):
            inputs, result = {}, {}

        best = None
        candidates = result.get("candidates", [])
        if candidates:
            best = candidates[0]

        comparison.append({
            "scenario_id": run.id,
            "status": run.status,
            "result_hash": run.result_hash,
            "inputs": inputs,
            "summary": result.get("summary", {}),
            "best_candidate": best,
            "feasible_count": len(candidates),
            "infeasible_count": len(result.get("infeasible", [])),
            "missing_data": result.get("missing_data", []),
            "assumptions": result.get("assumptions", []),
        })

    # Find changed inputs between runs
    base_inputs = comparison[0]["inputs"] if comparison else {}
    changed_inputs = {}
    for key, val in base_inputs.items():
        for comp in comparison[1:]:
            if comp["inputs"].get(key) != val:
                changed_inputs[key] = {
                    "base": val,
                    "others": [c["inputs"].get(key) for c in comparison[1:]],
                }

    return {
        "runs": comparison,
        "changed_inputs": changed_inputs,
        "shared_inputs": {k: v for k, v in base_inputs.items() if k not in changed_inputs},
        "hashes_match": len({c["result_hash"] for c in comparison}) == 1,
    }


@router.post("/{scenario_id}/promote")
def promote_scenario(
    scenario_id: str,
    body: PromoteBody,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(resolve_actor),
):
    """Promote (approve) a scenario option.

    V4-05: Only academic_ops may promote. Rechecks hard constraints before
    committing. Writes an audit record on the ScenarioRun.
    Promotion does NOT automatically mutate the canonical event — it records
    the human decision which a separate workflow step may then act on.
    """
    d = authorize(actor, "approve:scenario")
    if not d:
        raise HTTPException(
            status_code=403,
            detail={"reason_code": d.reason_code, "message": d.reason},
        )

    run = db.get(ScenarioRun, scenario_id)
    if run is None or run.tenant_id != actor.tenant_id:
        raise HTTPException(status_code=404, detail="Scenario not found.")

    if run.status not in ("computed",):
        raise HTTPException(
            status_code=409,
            detail={
                "reason_code": "SCENARIO_NOT_PROMOTABLE",
                "message": f"Scenario status is '{run.status}'; only 'computed' scenarios can be promoted.",
            },
        )

    # Verify the selected option exists in the result
    try:
        result = json.loads(run.result_json)
    except (json.JSONDecodeError, TypeError):
        result = {}

    candidate_ids = [c.get("option_id") for c in result.get("candidates", [])]
    if body.selected_option_id not in candidate_ids:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": "OPTION_NOT_FOUND",
                "message": f"Option '{body.selected_option_id}' not in feasible candidates. "
                           f"Available: {candidate_ids}",
            },
        )

    # Recheck hard constraints at promotion time
    try:
        inputs_dict = json.loads(run.inputs_json)
        inputs = ClassroomOutageInput(**{
            k: v for k, v in inputs_dict.items()
            if k in ClassroomOutageInput.__dataclass_fields__
        })
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "reason_code": "INPUTS_UNREADABLE",
                "message": f"Cannot recheck constraints: {exc}",
            },
        )

    # Re-run engine to validate constraints are still met
    recheck_id = "scn_recheck_" + uuid.uuid4().hex[:8]
    recheck = scenario_engine.run(db, inputs, recheck_id)
    recheck_ids = [c.option_id for c in recheck.candidates]
    if body.selected_option_id not in recheck_ids:
        raise HTTPException(
            status_code=409,
            detail={
                "reason_code": "CONSTRAINTS_NO_LONGER_MET",
                "message": (
                    f"Option '{body.selected_option_id}' no longer passes hard constraints "
                    f"(source data may have changed since the scenario was computed). "
                    f"Please rerun the scenario."
                ),
            },
        )

    # Stale check: if canonical_event has changed version since scenario was run
    if run.canonical_event_id:
        ce = db.get(CanonicalEvent, run.canonical_event_id)
        if ce and hasattr(ce, "version"):
            try:
                stored_inputs = json.loads(run.inputs_json)
                stored_version = stored_inputs.get("context_event_version")
                if stored_version is not None and ce.version != stored_version:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "reason_code": "SCENARIO_STALE",
                            "message": (
                                f"The canonical event has been updated (version {ce.version}) "
                                f"since this scenario was computed (version {stored_version}). "
                                "Please rerun the scenario with the current event state."
                            ),
                        },
                    )
            except (json.JSONDecodeError, TypeError):
                pass

    # Write promotion
    now = get_now()
    run.status = "promoted"
    run.promoted_by = actor.actor_id
    run.promoted_at = now
    run.promoted_option_id = body.selected_option_id
    run.promotion_rationale = body.rationale
    run.updated_at = now
    db.commit()
    db.refresh(run)

    return {
        "status": "promoted",
        "scenario_id": scenario_id,
        "promoted_option_id": body.selected_option_id,
        "promoted_by": actor.actor_id,
        "promoted_at": now.isoformat(),
        "note": "Canonical event and work items are not automatically updated. "
                "A workflow step must act on this decision.",
    }

"""Security watchdog API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import AuditEvent
from app.services.security import report as report_mod

router = APIRouter()

_SIMULATION_MESSAGE = "Simulation: no notification was sent to anyone."


@router.get("/watchdog")
def get_watchdog():
    """Return cached security report (run once if not yet cached)."""
    return report_mod.get_report()


@router.post("/watchdog/run")
def run_watchdog(db: Session = Depends(get_db)):
    """Re-run the security watchdog, record an audit event, return fresh report."""
    result = report_mod.run_report()
    db.add(AuditEvent(
        action="security_watchdog_run",
        resource_type="security_report",
        resource_id=None,
        result="success",
    ))
    db.commit()
    return result


@router.post("/findings/{finding_id}/escalate")
def escalate_finding(finding_id: str, db: Session = Depends(get_db)):
    """Write an audit event for simulated escalation. Returns simulation message."""
    finding = report_mod.get_finding_by_id(finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail=f"Finding '{finding_id}' not found")
    db.add(AuditEvent(
        action="escalated_to_it_simulated",
        resource_type="security_finding",
        resource_id=finding_id,
        result="simulated",
    ))
    db.commit()
    return {"status": "recorded", "message": _SIMULATION_MESSAGE}

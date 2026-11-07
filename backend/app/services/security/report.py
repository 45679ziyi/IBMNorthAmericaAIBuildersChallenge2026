"""Security watchdog orchestrator — loads assets/advisories, runs checks, caches result."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.services.security.models import SecurityFinding
from app.services.security.matcher import match_advisories, check_cert_expiry
from app.services.security.posture import check_posture

# Sample data paths
_SAMPLE_DATA = Path(__file__).parent.parent.parent.parent.parent / "sample-data"

_SCHEDULE_NOTE = (
    "Simulated daily check. To run it on a schedule, call "
    "python -m scripts.run_security_check from cron on the machine that hosts AURORA."
)


def _load_assets() -> list[dict[str, Any]]:
    path = _SAMPLE_DATA / "security_assets_demo.json"
    return json.loads(path.read_text()).get("assets", [])


def _load_advisories() -> list[dict[str, Any]]:
    path = _SAMPLE_DATA / "security_advisories_demo.json"
    return json.loads(path.read_text()).get("advisories", [])


# ─── Simple in-process cache ──────────────────────────────────────────────────

_cached_report: Optional[dict[str, Any]] = None


def _build_report(now: datetime | None = None) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    assets = _load_assets()
    advisories = _load_advisories()

    findings: list[SecurityFinding] = []
    findings.extend(match_advisories(assets, advisories, now=now))
    findings.extend(check_cert_expiry(assets, now=now))
    findings.extend(check_posture())

    # Stable ordering: severity rank → finding id
    _SEV_ORDER = {"critical": 0, "warn": 1, "info": 2}
    findings.sort(key=lambda f: (_SEV_ORDER.get(f.severity, 9), f.id))

    summary = {
        "critical": sum(1 for f in findings if f.severity == "critical"),
        "warn": sum(1 for f in findings if f.severity == "warn"),
        "info": sum(1 for f in findings if f.severity == "info"),
    }

    return {
        "last_run_at_utc": now.isoformat(),
        "schedule_note": _SCHEDULE_NOTE,
        "summary": summary,
        "findings": [_finding_to_dict(f) for f in findings],
    }


def _finding_to_dict(f: SecurityFinding) -> dict[str, Any]:
    return {
        "id": f.id,
        "kind": f.kind,
        "severity": f.severity,
        "title": f.title,
        "evidence": f.evidence,
        "affected_asset_ids": f.affected_asset_ids,
        "advisory_id": f.advisory_id,
        "status": f.status,
        "recommended_human_action": f.recommended_human_action,
        "detected_at_utc": f.detected_at_utc.isoformat(),
        "data_origin": f.data_origin,
        "automated_action": f.automated_action,
    }


def get_report() -> dict[str, Any]:
    """Return cached report, or run if no cache exists."""
    global _cached_report
    if _cached_report is None:
        _cached_report = _build_report()
    return _cached_report


def run_report(now: datetime | None = None) -> dict[str, Any]:
    """Re-run the watchdog and cache the result."""
    global _cached_report
    _cached_report = _build_report(now=now)
    return _cached_report


def clear_cache() -> None:
    """Clear the cached report (useful in tests)."""
    global _cached_report
    _cached_report = None


def get_finding_by_id(finding_id: str) -> Optional[SecurityFinding]:
    """Look up a finding by id from the current report."""
    report = get_report()
    for f in report["findings"]:
        if f["id"] == finding_id:
            return f
    return None

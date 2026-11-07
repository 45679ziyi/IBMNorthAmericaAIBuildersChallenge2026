"""Read-only AURORA configuration posture checks.

Checks only AURORA's own configuration — never touches external systems.
All findings have data_origin = 'local_config'.
"""
from __future__ import annotations

import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.security.models import SecurityFinding
from app.services.security.matcher import _finding_id


def _posture_finding(kind_suffix: str, severity: str, title: str, evidence: list[str], action: str) -> SecurityFinding:
    fid = _finding_id("config_posture", kind_suffix, [])
    return SecurityFinding(
        id=fid,
        kind="config_posture",
        severity=severity,
        title=title,
        evidence=evidence,
        affected_asset_ids=[],
        advisory_id=None,
        status="needs_human_review",
        recommended_human_action=action,
        detected_at_utc=datetime.now(timezone.utc),
        data_origin="local_config",
    )


def check_posture() -> list[SecurityFinding]:
    """Run all posture checks. Returns list of SecurityFinding."""
    findings: list[SecurityFinding] = []

    try:
        # 1. CORS wildcard check
        cors_origins = getattr(settings, "cors_origins", [])
        if isinstance(cors_origins, str):
            cors_origins = [o.strip() for o in cors_origins.split(",")]
        if "*" in cors_origins:
            findings.append(_posture_finding(
                "cors_wildcard", "info",
                "CORS allows all origins (*)",
                ["cors_origins contains '*'"],
                "Restrict CORS origins to known domains before production deployment.",
            ))

        # 2. Non-mock AI provider (data leaves machine)
        ai_provider = getattr(settings, "ai_provider", "mock").lower()
        if ai_provider and ai_provider != "mock":
            findings.append(_posture_finding(
                "ai_provider_external", "info",
                f"AI provider is set to '{ai_provider}' — data may leave the machine",
                [f"ai_provider={ai_provider}"],
                "Ensure data handling complies with institutional privacy policy.",
            ))

        # 3. DB file group/world readable
        db_url = getattr(settings, "database_url", "")
        if db_url.startswith("sqlite:///"):
            db_path_str = db_url[len("sqlite:///"):]
            db_path = Path(db_path_str)
            if db_path.exists():
                mode = db_path.stat().st_mode
                if mode & (stat.S_IRGRP | stat.S_IROTH):
                    findings.append(_posture_finding(
                        "db_permissive", "warn",
                        "Database file is group/world readable",
                        [f"File: {db_path_str}", f"Mode: {oct(mode & 0o777)}"],
                        "Run `chmod 600` on the database file to restrict access.",
                    ))

        # 4. .env with permissive mode
        env_path = Path(db_url[len("sqlite:///"):]).parent / ".env" if db_url.startswith("sqlite:///") else None
        # Also check common locations
        for env_candidate in [Path(".env"), Path("../.env"), Path("backend/.env")]:
            if env_candidate.exists():
                mode = env_candidate.stat().st_mode
                if mode & (stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH):
                    findings.append(_posture_finding(
                        "env_permissive", "warn",
                        ".env file has permissive permissions",
                        [f"File: {env_candidate}", f"Mode: {oct(mode & 0o777)}"],
                        "Run `chmod 600 .env` to restrict access to the env file.",
                    ))
                break  # only flag once

        # 5. Connector write capability check
        connectors = getattr(settings, "connectors", [])
        if isinstance(connectors, list):
            for conn in connectors:
                if isinstance(conn, dict) and conn.get("write_capability"):
                    findings.append(_posture_finding(
                        "connector_write", "warn",
                        f"Connector '{conn.get('name', '?')}' declares write capability",
                        [f"connector={conn.get('name')}", "write_capability=true"],
                        "Review connector permissions. No connector should have write access in demo mode.",
                    ))

    except Exception:
        pass  # posture checks are best-effort

    return findings

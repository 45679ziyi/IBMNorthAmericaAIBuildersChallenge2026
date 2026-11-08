"""Security advisory matcher — matches advisories against assets.

No external network calls. Semver-like comparator with no new dependencies.
Advisory text is sanitized before any use; it never affects matching logic.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from app.services.security.models import SecurityFinding


# ─── Advisory text safety ─────────────────────────────────────────────────────

def _sanitize_advisory_text(text: str, max_len: int = 500) -> str:
    """Strip control chars + HTML tags, cap at max_len chars."""
    # Remove HTML tags
    cleaned = re.sub(r"<[^>]*>", "", text)
    # Remove control characters (but keep newlines/spaces)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)
    return cleaned[:max_len]


# ─── Semver-like comparator ────────────────────────────────────────────────────

def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a version string like '1.9.0' into a tuple of ints."""
    parts = re.split(r"[.\-]", v)
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            break
    return tuple(result)


def _version_lt(v: str, limit: str) -> bool:
    """Return True if version v < limit."""
    return _parse_version(v) < _parse_version(limit)


def _version_gte(v: str, limit: str) -> bool:
    """Return True if version v >= limit."""
    return _parse_version(v) >= _parse_version(limit)


# ─── Finding id ───────────────────────────────────────────────────────────────

def _finding_id(kind: str, advisory_id: str | None, asset_ids: list[str]) -> str:
    raw = f"{kind}|{advisory_id or ''}|{'|'.join(sorted(asset_ids))}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


# ─── Cert expiry ──────────────────────────────────────────────────────────────

def check_cert_expiry(
    assets: list[dict[str, Any]],
    now: datetime | None = None,
) -> list[SecurityFinding]:
    """Return findings for certificates expiring within 30 days."""
    if now is None:
        from app.core.clock import get_now
        now = get_now()
    findings: list[SecurityFinding] = []
    for asset in assets:
        if asset.get("type") != "certificate":
            continue
        expires_str = asset.get("expires_at_utc")
        if not expires_str:
            continue
        expires = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
        days_left = (expires - now).days
        if days_left <= 7:
            sev = "critical"
            msg = f"Certificate expires in {days_left} day(s)"
        elif days_left <= 30:
            sev = "warn"
            msg = f"Certificate expires in {days_left} day(s)"
        else:
            continue
        fid = _finding_id("cert_expiry", None, [asset["id"]])
        findings.append(SecurityFinding(
            id=fid,
            kind="cert_expiry",
            severity=sev,
            title=f"Certificate expiry: {asset['name']}",
            evidence=[msg, f"Expires: {expires_str}", f"Issuer: {asset.get('issuer', 'unknown')}"],
            affected_asset_ids=[asset["id"]],
            advisory_id=None,
            status="needs_human_review",
            recommended_human_action="Renew certificate before expiry to avoid service disruption.",
            detected_at_utc=now,
            data_origin=asset.get("data_origin", "synthetic"),
        ))
    return findings


# ─── Advisory matching ────────────────────────────────────────────────────────

def match_advisories(
    assets: list[dict[str, Any]],
    advisories: list[dict[str, Any]],
    now: datetime | None = None,
) -> list[SecurityFinding]:
    """Match each advisory against the asset list. Returns advisory_match findings."""
    if now is None:
        from app.core.clock import get_now
        now = get_now()
    findings: list[SecurityFinding] = []

    for adv in advisories:
        affected = adv.get("affected", {})
        adv_type = affected.get("type")
        matched_asset_ids: list[str] = []

        for asset in assets:
            if adv_type == "certificate_issuer":
                # Match by certificate issuer field
                if asset.get("type") == "certificate" and asset.get("issuer") == affected.get("value"):
                    matched_asset_ids.append(asset["id"])

            elif adv_type == "software":
                if asset.get("type") == "software" and asset.get("name") == affected.get("name"):
                    ver = asset.get("version", "")
                    ver_lt = affected.get("version_lt")
                    ver_gte = affected.get("version_gte")
                    lt_ok = _version_lt(ver, ver_lt) if ver_lt else True
                    gte_ok = _version_gte(ver, ver_gte) if ver_gte else True
                    if lt_ok and gte_ok:
                        matched_asset_ids.append(asset["id"])

            elif adv_type == "firmware":
                if asset.get("type") == "firmware" and asset.get("name") == affected.get("name"):
                    ver = asset.get("version", "")
                    ver_lt = affected.get("version_lt")
                    ver_gte = affected.get("version_gte")
                    lt_ok = _version_lt(ver, ver_lt) if ver_lt else True
                    gte_ok = _version_gte(ver, ver_gte) if ver_gte else True
                    if lt_ok and gte_ok:
                        matched_asset_ids.append(asset["id"])

        if not matched_asset_ids:
            continue

        # Sanitize advisory text before use in evidence (never in matching logic)
        safe_summary = _sanitize_advisory_text(adv.get("summary", ""))
        safe_title = _sanitize_advisory_text(adv.get("title", ""))

        fid = _finding_id("advisory_match", adv["id"], matched_asset_ids)
        findings.append(SecurityFinding(
            id=fid,
            kind="advisory_match",
            severity=adv.get("severity", "info"),
            title=f"Advisory match: {safe_title[:100]}",
            evidence=[
                f"Advisory ID: {adv['id']}",
                f"Summary: {safe_summary}",
                f"Affected assets: {', '.join(matched_asset_ids)}",
            ],
            affected_asset_ids=matched_asset_ids,
            advisory_id=adv["id"],
            status="needs_human_review",
            recommended_human_action=_sanitize_advisory_text(adv.get("remediation", "Review and remediate.")),
            detected_at_utc=now,
            data_origin="synthetic",
        ))

    return findings

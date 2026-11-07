"""Security finding dataclass."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class SecurityFinding:
    id: str                         # first 12 hex of sha1 over kind+advisory_id+sorted asset ids
    kind: str                       # advisory_match | cert_expiry | config_posture
    severity: str                   # critical | warn | info
    title: str
    evidence: list[str]
    affected_asset_ids: list[str]
    advisory_id: Optional[str]
    status: str                     # always "needs_human_review"
    recommended_human_action: str
    detected_at_utc: datetime
    data_origin: str                # synthetic | local_config
    automated_action: None = None   # always None

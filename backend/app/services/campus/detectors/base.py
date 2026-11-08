"""
Shared MoveSpec dataclass used by all detectors.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MoveSpec:
    key: str
    kind: str
    audience: str
    policy: str
    urgency: str
    impact: str
    title: str
    summary: str
    why: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)

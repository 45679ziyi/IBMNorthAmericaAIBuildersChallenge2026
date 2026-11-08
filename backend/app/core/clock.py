"""
Central "now" for all backend code.
- In real mode: returns datetime.now(timezone.utc)
- In scenario mode: returns the virtual time stored in sim_state
Call get_now() everywhere; never call datetime.now() outside this module.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

_virtual_now: Optional[datetime] = None


def get_now() -> datetime:
    if _virtual_now is not None:
        return _virtual_now
    return datetime.now(timezone.utc)


def set_virtual_now(dt: Optional[datetime]) -> None:
    global _virtual_now
    _virtual_now = dt


def is_scenario_mode() -> bool:
    return _virtual_now is not None

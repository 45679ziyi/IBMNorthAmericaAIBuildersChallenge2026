"""
Shared pytest fixtures for AURORA backend tests.
Autouse fixtures that apply to ALL tests in this directory.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def reset_virtual_clock():
    """Ensure every test starts and ends in real time mode (no virtual clock leak)."""
    from app.core.clock import set_virtual_now
    set_virtual_now(None)
    yield
    set_virtual_now(None)

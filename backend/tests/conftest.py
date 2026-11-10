"""
Shared pytest fixtures for AURORA backend tests.
Autouse fixtures that apply to ALL tests in this directory.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add the project tools/ directory to sys.path so tests can import
# validate_tenant_pack from aurora-campus-intelligence/tools/
_TOOLS_DIR = Path(__file__).parents[2] / "tools"
if _TOOLS_DIR.exists() and str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))


@pytest.fixture(autouse=True)
def reset_virtual_clock():
    """Ensure every test starts and ends in real time mode (no virtual clock leak)."""
    from app.core.clock import set_virtual_now
    set_virtual_now(None)
    yield
    set_virtual_now(None)

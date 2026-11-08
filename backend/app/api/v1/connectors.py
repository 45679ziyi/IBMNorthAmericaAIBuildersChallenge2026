"""Connector status endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.clock import get_now
from app.schemas.schemas import ConnectorStatus
from app.core.config import settings

router = APIRouter()


@router.get("/status", response_model=list[ConnectorStatus])
def connector_status():
    now = get_now()
    return [
        ConnectorStatus(
            name="Calendar (ICS Import)",
            status="connected",
            description="User-imported .ics calendar files. No live SBU SOLAR connection.",
            last_checked=now,
            data_categories=["calendar events", "class schedule"],
            purpose="Display your personal schedule and feed the daily planner.",
            sends_to_external_model=False,
        ),
        ConnectorStatus(
            name="Brightspace (Demo Adapter)",
            status="demo",
            description=(
                "Synthetic sample announcements and assignments. "
                "No connection to SBU Brightspace. A future integration requires "
                "written SBU authorization and an approved OAuth app."
            ),
            last_checked=now,
            data_categories=["announcements (demo)", "assignments (demo)"],
            purpose="Demonstrate the inbox experience with fictional data only.",
            sends_to_external_model=False,
        ),
        ConnectorStatus(
            name="SOLAR (Placeholder)",
            status="unavailable",
            description=(
                "No live SOLAR connection in MVP. "
                "Import your schedule via an exported .ics file instead."
            ),
            last_checked=now,
            data_categories=["enrollment (placeholder)"],
            purpose="Future: display your official registered schedule.",
            sends_to_external_model=False,
        ),
        ConnectorStatus(
            name="Campus Knowledge Base",
            status="connected",
            description="Curated local excerpts from public SBU policy pages.",
            last_checked=now,
            data_categories=["public university policies", "public event info"],
            purpose="Ground the campus assistant in official public sources.",
            sends_to_external_model=settings.ai_provider != "mock",
        ),
        ConnectorStatus(
            name=f"AI Provider ({settings.ai_provider})",
            status="connected" if settings.ai_provider == "mock" else "connected",
            description=(
                "Deterministic mock provider (no external calls)."
                if settings.ai_provider == "mock"
                else f"External provider: {settings.ai_provider}. Questions may be sent for inference."
            ),
            last_checked=now,
            data_categories=["assistant questions"],
            purpose="Explain planner recommendations and answer campus questions.",
            sends_to_external_model=settings.ai_provider != "mock",
        ),
        ConnectorStatus(
            name=f"Weather ({settings.weather_provider})",
            status="connected" if settings.weather_provider == "sample" else "connected",
            description=(
                "Sample weather fixture (offline). No external API call."
                if settings.weather_provider == "sample"
                else f"Live weather provider: {settings.weather_provider}."
            ),
            last_checked=now,
            data_categories=["weather (campus area)"],
            purpose="Show a weather card on the Today screen.",
            sends_to_external_model=False,
        ),
        ConnectorStatus(
            name="Campus Pulse (Synthetic Only)",
            status="demo",
            description=(
                "SIMULATED DATA — NOT CONNECTED TO SBU SYSTEMS. "
                "Generated locally for demo purposes only."
            ),
            last_checked=now,
            data_categories=["synthetic sensor readings"],
            purpose="Demonstrate future campus operations intelligence architecture.",
            sends_to_external_model=False,
        ),
    ]

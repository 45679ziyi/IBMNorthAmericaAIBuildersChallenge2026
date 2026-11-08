"""Health check endpoint."""
from fastapi import APIRouter

from app.core.clock import get_now

from app.core.config import settings
from app.schemas.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version="0.1.0",
        database="sqlite",
        ai_provider=settings.ai_provider,
    )


@router.get("/dashboard/today")
async def dashboard_today():
    """Redirect — full implementation in the dashboard service."""
    from app.services.connectors.weather import get_weather_sample
    from app.core.config import settings

    now = get_now()
    return {
        "date": now.strftime("%Y-%m-%d"),
        "timezone": "America/New_York",
        "greeting": "Good day! Here's your AURORA overview.",
        "last_updated": now.isoformat(),
        "note": "Use /api/v1/events, /api/v1/tasks, etc. for full data.",
        "weather": get_weather_sample(),
    }

"""Weather adapter — sample fixture by default, optional live provider."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import settings


_SAMPLE_WEATHER = {
    "provider": "sample",
    "location": "Stony Brook, NY",
    "temperature_c": 12.5,
    "temperature_f": 54.5,
    "condition": "Partly Cloudy",
    "humidity_pct": 62,
    "wind_kmh": 18,
    "retrieved_at": None,
    "data_origin": "sample fixture",
    "disclaimer": "Weather data is a static sample. Enable a live provider via WEATHER_PROVIDER env variable.",
}


def get_weather_sample() -> dict[str, Any]:
    d = dict(_SAMPLE_WEATHER)
    d["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    return d

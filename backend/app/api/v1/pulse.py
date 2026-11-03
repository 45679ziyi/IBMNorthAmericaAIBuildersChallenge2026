"""Campus Pulse — synthetic sensor data only."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import random

from fastapi import APIRouter

from app.schemas.schemas import SensorReadingRead

router = APIRouter()

SENSORS = [
    ("Demo Building A / Room 101", "temperature", 21.5, "°C"),
    ("Demo Building A / Room 101", "air_quality", 42.0, "AQI"),
    ("Demo Building A / Room 101", "occupancy_count", 18.0, "people"),
    ("Demo Library / Study Room 3", "temperature", 22.1, "°C"),
    ("Demo Library / Study Room 3", "occupancy_count", 4.0, "people"),
    ("Demo Campus Center", "device_health", 98.0, "%"),
]

_DISCLAIMER = "SIMULATED DATA — NOT CONNECTED TO SBU SYSTEMS"


@router.get("/demo", response_model=list[SensorReadingRead])
def campus_pulse_demo():
    """Return synthetic sensor readings. data_origin is always 'synthetic'."""
    now = datetime.now(timezone.utc)
    readings = []
    for i, (label, metric, base_val, unit) in enumerate(SENSORS):
        jitter = random.uniform(-2.0, 2.0)
        readings.append(
            SensorReadingRead(
                id=f"synth-{i:03d}",
                sensor_label=label,
                metric_type=metric,
                value=round(base_val + jitter, 1),
                unit=unit,
                recorded_at_utc=now - timedelta(minutes=i),
                data_origin="synthetic",
            )
        )
    return readings

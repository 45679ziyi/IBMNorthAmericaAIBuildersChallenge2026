"""Deterministic campus sensor simulation.

All data is synthetic. `data_origin` is always 'synthetic'.
Readings are bucketed to 5-minute slots so the same bucket always
produces the same value (seeded random noise).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any


# ─── Sensor catalogue ─────────────────────────────────────────────────────────

@dataclass
class _SensorSpec:
    label: str
    metric: str
    unit: str
    base: float
    noise_range: float
    capacity: float | None = None  # for occupancy


_SENSORS: list[_SensorSpec] = [
    _SensorSpec("Demo Building A / Room 101", "temperature",     "°C",     21.5, 1.5),
    _SensorSpec("Demo Building A / Room 101", "air_quality",     "AQI",    42.0, 8.0),
    _SensorSpec("Demo Building A / Room 101", "occupancy_count", "people", 18.0, 4.0, capacity=30),
    _SensorSpec("Demo Library / Study Room 3","temperature",     "°C",     22.1, 1.0),
    _SensorSpec("Demo Library / Study Room 3","occupancy_count", "people",  4.0, 1.5, capacity=8),
    _SensorSpec("Demo Campus Center",         "device_health",   "%",      98.0, 1.5),
]


# ─── Time bucketing ───────────────────────────────────────────────────────────

def _bucket(ts: datetime) -> int:
    """5-minute time bucket (Unix seconds truncated to 300s)."""
    return int(ts.timestamp() // 300) * 300


# ─── Core value generator ─────────────────────────────────────────────────────

def _base_value(spec: _SensorSpec, bucket: int) -> float:
    """Deterministic value for a sensor at a given bucket."""
    rng = random.Random(f"{spec.label}|{spec.metric}|{bucket}")
    noise = rng.uniform(-spec.noise_range, spec.noise_range)
    return round(spec.base + noise, 1)


# ─── Public data structures ───────────────────────────────────────────────────

@dataclass
class SeriesPoint:
    recorded_at_utc: datetime
    value: float
    data_origin: str = "synthetic"


@dataclass
class SensorSeries:
    sensor_label: str
    metric_type: str
    unit: str
    capacity: float | None
    points: list[SeriesPoint] = field(default_factory=list)
    data_origin: str = "synthetic"


@dataclass
class LatestReading:
    id: str
    sensor_label: str
    metric_type: str
    value: float
    unit: str
    recorded_at_utc: datetime
    data_origin: str = "synthetic"


# ─── Generation functions ─────────────────────────────────────────────────────

def generate_latest(now: datetime | None = None) -> list[LatestReading]:
    """Return one deterministic reading per sensor for the current bucket."""
    if now is None:
        from app.core.clock import get_now
        now = get_now()
    b = _bucket(now)
    readings: list[LatestReading] = []
    for i, spec in enumerate(_SENSORS):
        val = _base_value(spec, b)
        readings.append(LatestReading(
            id=f"synth-{i:03d}",
            sensor_label=spec.label,
            metric_type=spec.metric,
            value=val,
            unit=spec.unit,
            recorded_at_utc=datetime.fromtimestamp(b, tz=timezone.utc),
            data_origin="synthetic",
        ))
    return readings


def generate_series(
    now: datetime | None = None,
    points: int = 24,
    scenario: str = "demo_incident",
) -> list[SensorSeries]:
    """Return per-sensor time-series over the most recent `points` buckets."""
    if now is None:
        from app.core.clock import get_now
        now = get_now()

    # Build bucket list: oldest first → newest last (index points-1 is newest)
    current_b = _bucket(now)
    buckets = [current_b - (points - 1 - i) * 300 for i in range(points)]

    series_map: dict[tuple[str, str], SensorSeries] = {}
    for spec in _SENSORS:
        key = (spec.label, spec.metric)
        series_map[key] = SensorSeries(
            sensor_label=spec.label,
            metric_type=spec.metric,
            unit=spec.unit,
            capacity=spec.capacity,
            points=[],
        )

    for i, b in enumerate(buckets):
        for spec in _SENSORS:
            key = (spec.label, spec.metric)
            val = _base_value(spec, b)

            # Apply scenario modifications to newest buckets
            if scenario == "demo_incident":
                step_from_newest = points - 1 - i
                # Room 101 temperature: drift +0.4°C per step over newest 8 buckets
                if spec.label == "Demo Building A / Room 101" and spec.metric == "temperature":
                    if step_from_newest < 8:
                        drift = (8 - step_from_newest) * 0.4
                        val = round(val + drift, 1)
                # Campus Center device_health: dip below 90 in newest 2 buckets
                if spec.label == "Demo Campus Center" and spec.metric == "device_health":
                    if step_from_newest < 2:
                        val = round(min(val, 88.5 - step_from_newest * 1.5), 1)

            series_map[key].points.append(SeriesPoint(
                recorded_at_utc=datetime.fromtimestamp(b, tz=timezone.utc),
                value=val,
            ))

    return list(series_map.values())

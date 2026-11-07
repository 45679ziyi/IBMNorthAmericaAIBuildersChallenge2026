"""Campus Pulse — synthetic sensor data only."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app.schemas.schemas import SensorReadingRead, PulseSeries, PulseSeriesPoint, PulseInsight
from app.services.ops import sim as sim_mod
from app.services.ops.analyzer import analyze

router = APIRouter()


@router.get("/demo", response_model=list[SensorReadingRead])
def campus_pulse_demo():
    """Return synthetic sensor readings (deterministic per 5-min bucket). data_origin='synthetic'."""
    now = datetime.now(timezone.utc)
    latest = sim_mod.generate_latest(now)
    return [
        SensorReadingRead(
            id=r.id,
            sensor_label=r.sensor_label,
            metric_type=r.metric_type,
            value=r.value,
            unit=r.unit,
            recorded_at_utc=r.recorded_at_utc,
            data_origin=r.data_origin,
        )
        for r in latest
    ]


@router.get("/series", response_model=list[PulseSeries])
def campus_pulse_series(
    points: int = Query(default=24, ge=1, le=288),
    scenario: str = Query(default="demo_incident"),
):
    """Return per-sensor time-series for the last `points` 5-minute buckets."""
    now = datetime.now(timezone.utc)
    series_list = sim_mod.generate_series(now=now, points=points, scenario=scenario)
    result: list[PulseSeries] = []
    for s in series_list:
        result.append(PulseSeries(
            sensor_label=s.sensor_label,
            metric_type=s.metric_type,
            unit=s.unit,
            capacity=s.capacity,
            points=[
                PulseSeriesPoint(
                    recorded_at_utc=p.recorded_at_utc,
                    value=p.value,
                    data_origin=p.data_origin,
                )
                for p in s.points
            ],
            data_origin=s.data_origin,
        ))
    return result


@router.get("/insights", response_model=list[PulseInsight])
def campus_pulse_insights(
    scenario: str = Query(default="demo_incident"),
):
    """Return rule-based insights from the current sensor series."""
    now = datetime.now(timezone.utc)
    series_list = sim_mod.generate_series(now=now, points=24, scenario=scenario)
    raw_insights = analyze(series_list)
    return [
        PulseInsight(
            id=ins.id,
            severity=ins.severity,
            sensor_label=ins.sensor_label,
            metric_type=ins.metric_type,
            message=ins.message,
            evidence=ins.evidence,
            recommended_human_action=ins.recommended_human_action,
            automated_action=ins.automated_action,
            status=ins.status,
            data_origin=ins.data_origin,
        )
        for ins in raw_insights
    ]

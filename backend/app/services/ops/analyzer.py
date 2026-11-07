"""Campus sensor data analyzer — rules-based insight generation.

No ML. Deterministic rules + least-squares trend detection.
All insights have `automated_action=None` and `status='needs_human_review'`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from app.services.ops.sim import SensorSeries


# ─── Insight data structure ────────────────────────────────────────────────────

@dataclass
class PulseInsight:
    id: str
    severity: str          # "info" | "warn" | "critical"
    sensor_label: str
    metric_type: str
    message: str
    evidence: dict[str, Any]
    recommended_human_action: str
    automated_action: None = None
    status: str = "needs_human_review"
    data_origin: str = "synthetic"


# ─── Rule thresholds ──────────────────────────────────────────────────────────

_TEMP_WARN_LOW  = 20.0
_TEMP_WARN_HIGH = 24.0
_TEMP_CRIT_LOW  = 16.0
_TEMP_CRIT_HIGH = 28.0

_AQI_WARN     = 100.0
_AQI_CRITICAL = 150.0

_OCC_WARN_RATIO  = 0.9
_OCC_CRIT_RATIO  = 1.0

_HEALTH_WARN  = 95.0
_HEALTH_CRIT  = 85.0

_TREND_STEPS  = 8   # newest N points used for trend
_TREND_PROJ   = 8   # project N steps ahead


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _least_squares_slope(values: list[float]) -> float:
    """Return slope (units per step) from a sequence of equally-spaced values."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    return num / den


def _make_id(label: str, metric: str, kind: str) -> str:
    """Short stable id for an insight."""
    import hashlib
    raw = f"{label}|{metric}|{kind}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


# ─── Per-metric rule checkers ─────────────────────────────────────────────────

def _check_temperature(series: SensorSeries) -> list[PulseInsight]:
    insights: list[PulseInsight] = []
    if not series.points:
        return insights
    latest = series.points[-1].value
    trend_vals = [p.value for p in series.points[-_TREND_STEPS:]]
    slope = _least_squares_slope(trend_vals)
    projected = latest + slope * _TREND_PROJ

    # Threshold checks
    if latest > _TEMP_CRIT_HIGH or latest < _TEMP_CRIT_LOW:
        sev = "critical"
        msg = f"Temperature critical: {latest}°C (comfort: {_TEMP_WARN_LOW}–{_TEMP_WARN_HIGH}°C)"
        action = "Inspect HVAC immediately. Alert facilities management."
    elif latest > _TEMP_WARN_HIGH or latest < _TEMP_WARN_LOW:
        sev = "warn"
        msg = f"Temperature out of comfort range: {latest}°C"
        action = "Check HVAC settings and notify facilities if persistent."
    else:
        sev = None
        msg = ""
        action = ""

    if sev:
        insights.append(PulseInsight(
            id=_make_id(series.sensor_label, series.metric_type, "threshold"),
            severity=sev,
            sensor_label=series.sensor_label,
            metric_type=series.metric_type,
            message=msg,
            evidence={"latest_value": latest, "unit": series.unit, "slope_per_step": round(slope, 4)},
            recommended_human_action=action,
        ))

    # Trend check (even if threshold not hit)
    if abs(slope) > 0:
        if slope > 0 and projected > _TEMP_WARN_HIGH and latest <= _TEMP_WARN_HIGH:
            insights.append(PulseInsight(
                id=_make_id(series.sensor_label, series.metric_type, "rising_trend"),
                severity="warn",
                sensor_label=series.sensor_label,
                metric_type=series.metric_type,
                message=f"Temperature rising trend: projected {round(projected, 1)}°C in {_TREND_PROJ} steps",
                evidence={"latest_value": latest, "slope_per_step": round(slope, 4), "projected": round(projected, 1)},
                recommended_human_action="Monitor HVAC. Adjust cooling if trend continues.",
            ))
        elif slope < 0 and projected < _TEMP_WARN_LOW and latest >= _TEMP_WARN_LOW:
            insights.append(PulseInsight(
                id=_make_id(series.sensor_label, series.metric_type, "falling_trend"),
                severity="warn",
                sensor_label=series.sensor_label,
                metric_type=series.metric_type,
                message=f"Temperature falling trend: projected {round(projected, 1)}°C in {_TREND_PROJ} steps",
                evidence={"latest_value": latest, "slope_per_step": round(slope, 4), "projected": round(projected, 1)},
                recommended_human_action="Monitor heating system. Adjust if trend continues.",
            ))
    return insights


def _check_air_quality(series: SensorSeries) -> list[PulseInsight]:
    insights: list[PulseInsight] = []
    if not series.points:
        return insights
    latest = series.points[-1].value
    if latest > _AQI_CRITICAL:
        sev, msg = "critical", f"Air quality critical AQI {latest}"
        action = "Open ventilation, evacuate if persistent above 200. Contact facilities."
    elif latest > _AQI_WARN:
        sev, msg = "warn", f"Air quality elevated AQI {latest}"
        action = "Increase ventilation. Monitor for further increase."
    else:
        return insights
    insights.append(PulseInsight(
        id=_make_id(series.sensor_label, series.metric_type, "threshold"),
        severity=sev,
        sensor_label=series.sensor_label,
        metric_type=series.metric_type,
        message=msg,
        evidence={"latest_value": latest, "unit": series.unit},
        recommended_human_action=action,
    ))
    return insights


def _check_occupancy(series: SensorSeries) -> list[PulseInsight]:
    insights: list[PulseInsight] = []
    if not series.points or series.capacity is None:
        return insights
    latest = series.points[-1].value
    ratio = latest / series.capacity
    if ratio > _OCC_CRIT_RATIO:
        sev, msg = "critical", f"Occupancy over capacity: {int(latest)}/{int(series.capacity)}"
        action = "Redirect occupants immediately. Alert safety officers."
    elif ratio > _OCC_WARN_RATIO:
        sev, msg = "warn", f"Occupancy near capacity: {int(latest)}/{int(series.capacity)} ({round(ratio*100)}%)"
        action = "Monitor closely. Prepare to redirect occupants if capacity is reached."
    else:
        return insights
    insights.append(PulseInsight(
        id=_make_id(series.sensor_label, series.metric_type, "threshold"),
        severity=sev,
        sensor_label=series.sensor_label,
        metric_type=series.metric_type,
        message=msg,
        evidence={"latest_value": latest, "capacity": series.capacity, "ratio": round(ratio, 3)},
        recommended_human_action=action,
    ))
    return insights


def _check_device_health(series: SensorSeries) -> list[PulseInsight]:
    insights: list[PulseInsight] = []
    if not series.points:
        return insights
    latest = series.points[-1].value
    if latest < _HEALTH_CRIT:
        sev, msg = "critical", f"Device health critical: {latest}%"
        action = "Immediately inspect device infrastructure. Escalate to IT."
    elif latest < _HEALTH_WARN:
        sev, msg = "warn", f"Device health degraded: {latest}%"
        action = "Schedule device inspection. Review error logs."
    else:
        return insights
    insights.append(PulseInsight(
        id=_make_id(series.sensor_label, series.metric_type, "threshold"),
        severity=sev,
        sensor_label=series.sensor_label,
        metric_type=series.metric_type,
        message=msg,
        evidence={"latest_value": latest, "unit": series.unit},
        recommended_human_action=action,
    ))
    return insights


# ─── Public API ───────────────────────────────────────────────────────────────

_CHECKER_MAP = {
    "temperature":     _check_temperature,
    "air_quality":     _check_air_quality,
    "occupancy_count": _check_occupancy,
    "device_health":   _check_device_health,
}


def analyze(series_list: list[SensorSeries]) -> list[PulseInsight]:
    """Run all rules against a list of sensor series. Returns PulseInsight list."""
    all_insights: list[PulseInsight] = []
    for series in series_list:
        checker = _CHECKER_MAP.get(series.metric_type)
        if checker:
            all_insights.extend(checker(series))
    return all_insights

"""Outdoor air-quality helpers: PM2.5 -> India NAQI sub-index, severity labels, alert."""
from __future__ import annotations

import math
from enum import Enum

from app.assumptions import ALERT_AQI
from app.models import MAX_AQI

# (pm25_low, pm25_high, index_low, index_high), following CPCB NAQI PM2.5 bands.
_PM25_BANDS = (
    (0, 30, 0, 50),
    (30, 60, 51, 100),
    (60, 90, 101, 200),
    (90, 120, 201, 300),
    (120, 250, 301, 400),
    (250, 380, 401, 500),
)


class Severity(str, Enum):
    GOOD = "good"
    SATISFACTORY = "satisfactory"
    MODERATE = "moderate"
    POOR = "poor"
    VERY_POOR = "very_poor"
    SEVERE = "severe"


_SEVERITY_LIMITS = (
    (50, Severity.GOOD),
    (100, Severity.SATISFACTORY),
    (200, Severity.MODERATE),
    (300, Severity.POOR),
    (400, Severity.VERY_POOR),
)


def _non_negative(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if math.isnan(value) or value < 0:
        raise ValueError(f"{name} must be a non-negative number")
    return float(value)


def normalize_aqi(value: float) -> float:
    """Validate an AQI reading and cap it at the top of the scale."""
    return min(_non_negative(value, "AQI"), float(MAX_AQI))


def pm25_to_naqi(pm25: float) -> int:
    """Convert a PM2.5 concentration (ug/m3) to an NAQI sub-index (0-500).

    Approximation: CPCB uses 24-hour averages, we apply the bands to the reading
    we have. Documented in the README.
    """
    pm25 = _non_negative(pm25, "PM2.5")
    for low, high, index_low, index_high in _PM25_BANDS:
        if pm25 <= high:
            return round(index_low + (index_high - index_low) * (pm25 - low) / (high - low))
    return MAX_AQI


def naqi_to_pm25(aqi: float) -> float:
    """The PM2.5 (ug/m3) that corresponds to an index value on the same scale (for showing units)."""
    aqi = normalize_aqi(aqi)
    for low, high, index_low, index_high in _PM25_BANDS:
        if aqi <= index_high:
            span = (index_high - index_low) or 1
            return round(low + (high - low) * max(aqi - index_low, 0) / span, 1)
    return float(_PM25_BANDS[-1][1])


def severity(aqi: float) -> Severity:
    aqi = normalize_aqi(aqi)
    for limit, label in _SEVERITY_LIMITS:
        if aqi <= limit:
            return label
    return Severity.SEVERE


def severity_alert(aqi: float) -> str | None:
    """One-line safety alert shown without being asked, only when air is dangerous."""
    if normalize_aqi(aqi) < ALERT_AQI:
        return None
    return (
        "Air quality is dangerous today: limit time outdoors, especially for "
        "children, older adults and anyone with breathing problems."
    )

"""Best-time suggestion. Only used when the user says their timing is flexible."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app import assumptions as A


@dataclass(frozen=True)
class TimeSuggestion:
    hour: int
    forecast_aqi: float
    current_aqi: float
    improvement_pct: int


def suggest_better_time(
    hourly_aqi: Mapping[int, float], current_hour: int
) -> TimeSuggestion | None:
    """Cleanest daytime hour later today, or None if it is not meaningfully better."""
    current = hourly_aqi.get(current_hour)
    if current is None or current <= 0:
        return None
    later = {h: v for h, v in hourly_aqi.items() if h > current_hour and h in A.CLEAN_HOURS}
    if not later:
        return None
    best_hour = min(later, key=lambda h: (later[h], h))
    gain = (current - later[best_hour]) / current
    if gain < A.MIN_TIMING_IMPROVEMENT:
        return None
    return TimeSuggestion(best_hour, later[best_hour], current, round(gain * 100))

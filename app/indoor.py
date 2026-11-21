"""Indoor air estimate and the ranked 'what to fix first' list.

Model:  indoor = outdoor * infiltration  +  indoor sources  ->  x (1 - purifier)
It is a transparent estimate, never a measurement. Every step is recorded as a
Factor so the UI (and Gemini) can explain exactly why the number is what it is.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from app import assumptions as A
from app.aqi import Severity, normalize_aqi, severity
from app.models import MAX_AQI, CookingFuel, Heating, HomeProfile, WindowHabit


@dataclass(frozen=True)
class Factor:
    code: str
    effect: int  # AQI points: positive worsens indoor air, negative improves it


@dataclass(frozen=True)
class IndoorEstimate:
    score: int
    low: int
    high: int
    severity: Severity
    factors: tuple[Factor, ...]


@dataclass(frozen=True)
class Fix:
    code: str
    points_saved: int
    new_score: int


def estimate_indoor_aqi(outdoor_aqi: float, home: HomeProfile) -> IndoorEstimate:
    outdoor = normalize_aqi(outdoor_aqi)
    factors: list[Factor] = []

    value = outdoor * A.INFILTRATION[home.windows]
    factors.append(Factor(f"windows_{home.windows.value}", round(value - outdoor)))

    cooking = A.COOKING_SOURCE_POINTS[home.cooking]
    if home.has_kitchen_exhaust:
        cooking *= 1 - A.EXHAUST_REDUCTION
    sources = (
        (f"cooking_{home.cooking.value}", cooking),
        (f"heating_{home.heating.value}", A.HEATING_SOURCE_POINTS[home.heating]),
        ("incense", A.INCENSE_POINTS if home.burns_incense else 0),
        ("indoor_smoking", A.SMOKING_POINTS if home.indoor_smoking else 0),
    )
    for code, points in sources:
        value += points
        if points:
            factors.append(Factor(code, round(points)))

    if home.has_purifier:
        removed = value * A.PURIFIER_REDUCTION
        value -= removed
        factors.append(Factor("purifier", -round(removed)))

    value = min(max(value, 0), MAX_AQI)
    return IndoorEstimate(
        score=round(value),
        low=round(value * (1 - A.ESTIMATE_UNCERTAINTY)),
        high=min(MAX_AQI, round(value * (1 + A.ESTIMATE_UNCERTAINTY))),
        severity=severity(value),
        factors=tuple(factors),
    )


def _candidate_changes(home: HomeProfile) -> dict[str, HomeProfile]:
    """Every single change the household could make, applied to a copy."""
    changes: dict[str, HomeProfile] = {}
    if home.windows is not WindowHabit.CLOSED:
        changes["close_windows"] = replace(home, windows=WindowHabit.CLOSED)
    if not home.has_purifier:
        changes["run_purifier"] = replace(home, has_purifier=True)  # DIY box-fan filter counts
    if home.cooking is not CookingFuel.ELECTRIC and not home.has_kitchen_exhaust:
        changes["use_kitchen_exhaust"] = replace(home, has_kitchen_exhaust=True)
    if home.cooking is not CookingFuel.ELECTRIC:
        changes["switch_to_electric_cooking"] = replace(home, cooking=CookingFuel.ELECTRIC)
    if home.burns_incense:
        changes["stop_incense"] = replace(home, burns_incense=False)
    if home.indoor_smoking:
        changes["stop_indoor_smoking"] = replace(home, indoor_smoking=False)
    if home.heating is Heating.COMBUSTION:
        changes["stop_burning_for_heat"] = replace(home, heating=Heating.NONE)
    return changes


def suggest_fixes(outdoor_aqi: float, home: HomeProfile) -> tuple[Fix, ...]:
    """Top fixes ranked by how many AQI points each would save (measured, not guessed)."""
    baseline = estimate_indoor_aqi(outdoor_aqi, home).score
    fixes = []
    for code, changed in _candidate_changes(home).items():
        new_score = estimate_indoor_aqi(outdoor_aqi, changed).score
        if baseline - new_score > 0:
            fixes.append(Fix(code, baseline - new_score, new_score))
    fixes.sort(key=lambda f: (-f.points_saved, f.code))
    return tuple(fixes[: A.MAX_FIXES])

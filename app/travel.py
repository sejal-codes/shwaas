"""Travel-mode comparison that weighs exposure AND emissions.

Rule of thumb: pick the lowest-emission option that is still safe for this person.
A private car is only recommended when nothing cleaner is available and safe.
"""
from __future__ import annotations

from dataclasses import dataclass

from app import assumptions as A
from app.aqi import normalize_aqi
from app.models import Plan, Profile, TravelMode


@dataclass(frozen=True)
class ModeOption:
    mode: TravelMode
    minutes: int
    exposure_aqi_hours: float  # AQI x hours of pollution breathed (no mask)
    co2_kg: float
    co2_saved_vs_car_kg: float


@dataclass(frozen=True)
class TravelRecommendation:
    options: tuple[ModeOption, ...]  # best first
    recommended: ModeOption | None
    car_is_fallback: bool  # True when the private car is the only sensible option
    no_safe_option: bool  # True when every option was open-air and above the avoid level


def _group(profile: Profile) -> str:
    return "adult" if profile is Profile.ADULT else "vulnerable"


def _is_feasible(mode: TravelMode, plan: Plan, profile: Profile) -> bool:
    if mode is TravelMode.WALK:
        return plan.distance_km <= A.MAX_WALK_KM[_group(profile)]
    if mode is TravelMode.CYCLE:
        return plan.distance_km <= A.MAX_CYCLE_KM and profile is not Profile.ELDERLY
    return True


def _is_safe(mode: TravelMode, plan: Plan, profile: Profile, aqi: float) -> bool:
    if mode not in A.OPEN_AIR_MODES or plan.distance_km <= A.SHORT_TRIP_KM:
        return True
    return aqi < A.OPEN_AIR_AVOID_AQI[_group(profile)]


def _co2_kg(mode: TravelMode, distance_km: float) -> float:
    return round(A.MODE_CO2_G_PER_KM[mode] * distance_km / 1000, 3)


def _build_option(mode: TravelMode, plan: Plan, aqi: float) -> ModeOption:
    minutes = max(1, round(plan.distance_km / A.MODE_SPEED_KMH[mode] * 60))
    open_minutes = minutes * A.MODE_EXPOSURE_FACTOR[mode] + A.MODE_ACCESS_MINUTES.get(mode, 0)
    car_co2 = _co2_kg(TravelMode.PRIVATE_CAR, plan.distance_km)
    co2 = _co2_kg(mode, plan.distance_km)
    return ModeOption(
        mode=mode,
        minutes=minutes + A.MODE_ACCESS_MINUTES.get(mode, 0),
        exposure_aqi_hours=round(aqi * open_minutes / 60, 1),
        co2_kg=co2,
        co2_saved_vs_car_kg=round(car_co2 - co2, 3),
    )


def rank_modes(plan: Plan, profile: Profile, outdoor_aqi: float) -> TravelRecommendation:
    aqi = normalize_aqi(outdoor_aqi)
    feasible = [m for m in plan.available_modes if _is_feasible(m, plan, profile)]
    safe = [m for m in feasible if _is_safe(m, plan, profile, aqi)]
    no_safe_option = bool(feasible) and not safe
    pool = safe or feasible

    options = sorted(
        (_build_option(m, plan, aqi) for m in pool),
        key=lambda o: (o.co2_kg, o.exposure_aqi_hours, o.mode.value),
    )
    recommended = options[0] if options else None
    return TravelRecommendation(
        options=tuple(options),
        recommended=recommended,
        car_is_fallback=recommended is not None and recommended.mode is TravelMode.PRIVATE_CAR,
        no_safe_option=no_safe_option,
    )

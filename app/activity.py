"""Activity advice for the 'planning something?' box.

Principles:
  * Essential activities (school, work, medical) are never skipped or postponed.
  * Optional activities may get an indoor alternative when the air is bad.
  * Timing advice appears only when the user says their timing is flexible.
  * Travel advice weighs exposure and emissions together (see travel.py).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from app import assumptions as A
from app.aqi import normalize_aqi
from app.models import ActivityKind, HomeProfile, Plan, Profile, Timing, traveller_profile
from app.timing import TimeSuggestion, suggest_better_time
from app.travel import TravelRecommendation, rank_modes

DISCLAIMER = "General guidance based on estimates, not medical advice."


class MaskLevel(str, Enum):
    NONE = "none"
    OPTIONAL = "optional"
    RECOMMENDED = "recommended"


@dataclass(frozen=True)
class MaskAdvice:
    level: MaskLevel
    fit_tips: tuple[str, ...]
    exposure_reduction_pct: int  # estimated, only when a mask is recommended


@dataclass(frozen=True)
class ActivityAdvice:
    mask: MaskAdvice
    travel: TravelRecommendation | None
    duration_tips: tuple[str, ...]
    before_after_tips: tuple[str, ...]
    recovery_tips: tuple[str, ...]
    better_time: TimeSuggestion | None
    optional_alternative: str | None
    disclaimer: str = DISCLAIMER


_FIT_TIPS = (
    "Use an N95/FFP2-type mask. Cloth and surgical masks do little against fine smoke particles.",
    "Press the nose clip down and check there are no gaps at the cheeks. A loose mask barely helps.",
)
_CHILD_FIT_TIP = (
    "For children, use a kid-sized N95-type mask only if it seals snugly. "
    "If it does not fit, do not force it. Rely on a shorter trip and a closed vehicle instead."
)
_DURATION_TIPS = (
    "Drop off or stop as close to the destination as is safe, to spend fewer minutes outside.",
    "Combine errands into one trip and skip optional stops.",
    "Wait indoors or inside the vehicle rather than standing outside.",
)
_BEFORE_AFTER_TIPS = (
    "Before leaving: keep windows shut and the purifier (or a DIY box-fan filter) running "
    "so you come back to cleaner air. Keep your mask by the door.",
    "On return: leave shoes at the door and change out of outdoor clothes.",
    "Do not put the outdoor bag or jacket on beds or sofas.",
)
_RECOVERY_FULL = (
    "Wash your face and hands.",
    "Rinse your nose with saline water.",
    "Drink some water.",
    "Rest in the cleanest room, with the purifier on if you have one.",
)
_RECOVERY_SIMPLE = (
    "Wash face and hands, and change clothes.",
    "Rest in the cleanest room, with the purifier on if you have one.",
)
_OPTIONAL_INDOOR = (
    "Move this indoors today (stretching, yoga, a home workout or a walk around the house)."
)
_OPTIONAL_EASY = "Keep it short and light today, and wear a well-fitted N95."


def _mask_advice(aqi: float, profile: Profile) -> MaskAdvice:
    if aqi <= A.MASK_OPTIONAL_AQI:
        return MaskAdvice(MaskLevel.NONE, (), 0)
    vulnerable = profile is not Profile.ADULT
    if aqi <= A.MASK_RECOMMENDED_AQI and not vulnerable:
        level = MaskLevel.OPTIONAL
    else:
        level = MaskLevel.RECOMMENDED
    tips = _FIT_TIPS + ((_CHILD_FIT_TIP,) if profile is Profile.FAMILY_WITH_CHILDREN else ())
    return MaskAdvice(level, tips, round((1 - A.N95_PENETRATION) * 100))


def _optional_alternative(plan: Plan, aqi: float) -> str | None:
    """Only optional, non-travel activities may be moved indoors. Never essential ones."""
    if plan.essential or plan.kind not in (ActivityKind.EXERCISE, ActivityKind.LEISURE):
        return None
    if aqi >= A.MASK_RECOMMENDED_AQI:
        return _OPTIONAL_INDOOR
    if aqi > A.MASK_OPTIONAL_AQI:
        return _OPTIONAL_EASY
    return None


def advise(
    plan: Plan,
    home: HomeProfile,
    outdoor_aqi: float,
    *,
    current_hour: int | None = None,
    hourly_aqi: Mapping[int, float] | None = None,
) -> ActivityAdvice:
    aqi = normalize_aqi(outdoor_aqi)
    traveller = traveller_profile(plan, home.profile)
    precautions = aqi > A.MASK_OPTIONAL_AQI  # in clean air, skip the extra-care tips
    travel = (
        rank_modes(plan, traveller, aqi)
        if plan.involves_travel and plan.distance_km > 0
        else None
    )
    better_time = None
    if plan.timing is Timing.FLEXIBLE and hourly_aqi and current_hour is not None:
        better_time = suggest_better_time(hourly_aqi, current_hour)

    return ActivityAdvice(
        mask=_mask_advice(aqi, traveller),
        travel=travel,
        duration_tips=_DURATION_TIPS if plan.involves_travel and precautions else (),
        before_after_tips=_BEFORE_AFTER_TIPS if precautions else (),
        recovery_tips=((_RECOVERY_FULL if traveller is Profile.ADULT else _RECOVERY_SIMPLE) if precautions else ()),
        better_time=better_time,
        optional_alternative=_optional_alternative(plan, aqi),
    )

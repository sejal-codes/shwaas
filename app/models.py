"""Data models and strict input validation.

Everything that enters the rule engine (from the UI or from Gemini's parsing of
free text) is converted into these immutable objects first. Invalid input raises
ValueError, so the rules never see malformed data.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, TypeVar

MAX_AQI = 500
MAX_DISTANCE_KM = 200.0

E = TypeVar("E", bound=Enum)


class Profile(str, Enum):
    FAMILY_WITH_CHILDREN = "family_with_children"
    ELDERLY = "elderly"
    ADULT = "adult"


class WindowHabit(str, Enum):
    OPEN = "open"
    SOMETIMES = "sometimes"
    CLOSED = "closed"


class CookingFuel(str, Enum):
    GAS = "gas"
    ELECTRIC = "electric"  # induction / electric hob
    BIOMASS = "biomass"  # wood, dung cake, coal chulha


class Heating(str, Enum):
    NONE = "none"
    ELECTRIC = "electric"
    COMBUSTION = "combustion"  # burning wood, coal, waste


class ActivityKind(str, Enum):
    SCHOOL_RUN = "school_run"
    WORK_COMMUTE = "work_commute"
    MEDICAL = "medical"
    ERRAND = "errand"
    EXERCISE = "exercise"
    LEISURE = "leisure"


ESSENTIAL_KINDS = frozenset(
    {ActivityKind.SCHOOL_RUN, ActivityKind.WORK_COMMUTE, ActivityKind.MEDICAL}
)
TRAVEL_KINDS = frozenset(
    {
        ActivityKind.SCHOOL_RUN,
        ActivityKind.WORK_COMMUTE,
        ActivityKind.MEDICAL,
        ActivityKind.ERRAND,
    }
)


class Timing(str, Enum):
    FIXED = "fixed"
    FLEXIBLE = "flexible"


class TravelMode(str, Enum):
    WALK = "walk"
    CYCLE = "cycle"
    TWO_WHEELER = "two_wheeler"
    E_RICKSHAW = "e_rickshaw"
    METRO_BUS = "metro_bus"
    CARPOOL = "carpool"
    PRIVATE_CAR = "private_car"


# ---------------------------------------------------------------- validation
def _enum(cls: type[E], value: Any, field: str) -> E:
    try:
        return cls(value)
    except ValueError:
        allowed = ", ".join(m.value for m in cls)
        raise ValueError(f"'{field}' must be one of: {allowed}") from None


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"'{field}' must be true or false")
    return value


def _require(data: Mapping[str, Any], field: str) -> Any:
    if field not in data:
        raise ValueError(f"'{field}' is required")
    return data[field]


# -------------------------------------------------------------------- models
@dataclass(frozen=True)
class HomeProfile:
    """Who lives at home and how the home behaves. Drives the indoor estimate."""

    profile: Profile
    windows: WindowHabit
    cooking: CookingFuel
    heating: Heating = Heating.NONE
    has_purifier: bool = False
    has_kitchen_exhaust: bool = False
    burns_incense: bool = False
    indoor_smoking: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HomeProfile":
        return cls(
            profile=_enum(Profile, _require(data, "profile"), "profile"),
            windows=_enum(WindowHabit, _require(data, "windows"), "windows"),
            cooking=_enum(CookingFuel, _require(data, "cooking"), "cooking"),
            heating=_enum(Heating, data.get("heating", "none"), "heating"),
            has_purifier=_bool(data.get("has_purifier", False), "has_purifier"),
            has_kitchen_exhaust=_bool(
                data.get("has_kitchen_exhaust", False), "has_kitchen_exhaust"
            ),
            burns_incense=_bool(data.get("burns_incense", False), "burns_incense"),
            indoor_smoking=_bool(data.get("indoor_smoking", False), "indoor_smoking"),
        )


@dataclass(frozen=True)
class Plan:
    """A structured version of what the user typed in the 'planning something' box."""

    kind: ActivityKind
    timing: Timing
    distance_km: float = 0.0
    available_modes: frozenset[TravelMode] = frozenset(TravelMode)

    def __post_init__(self) -> None:
        if not 0 <= self.distance_km <= MAX_DISTANCE_KM:
            raise ValueError(f"'distance_km' must be between 0 and {MAX_DISTANCE_KM:g}")
        if self.involves_travel and self.distance_km > 0 and not self.available_modes:
            raise ValueError("'available_modes' must not be empty for a trip")

    @property
    def essential(self) -> bool:
        return self.kind in ESSENTIAL_KINDS

    @property
    def involves_travel(self) -> bool:
        return self.kind in TRAVEL_KINDS

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Plan":
        raw_modes = data.get("available_modes")
        if raw_modes is None:
            modes = frozenset(TravelMode)
        elif isinstance(raw_modes, (list, tuple, set, frozenset)):
            modes = frozenset(_enum(TravelMode, m, "available_modes") for m in raw_modes)
        else:
            raise ValueError("'available_modes' must be a list")
        distance = data.get("distance_km", 0.0)
        if isinstance(distance, bool) or not isinstance(distance, (int, float)):
            raise ValueError("'distance_km' must be a number")
        return cls(
            kind=_enum(ActivityKind, _require(data, "kind"), "kind"),
            timing=_enum(Timing, _require(data, "timing"), "timing"),
            distance_km=float(distance),
            available_modes=modes,
        )


def traveller_profile(plan: Plan, household: Profile) -> Profile:
    """Who is actually out in the air on this plan.

    Children only travel on a school run. On any other plan the traveller from a family household is
    an adult, so child-specific rules (stricter travel limits, kid mask tips) apply to school runs only.
    """
    if household is Profile.FAMILY_WITH_CHILDREN and plan.kind is not ActivityKind.SCHOOL_RUN:
        return Profile.ADULT
    return household

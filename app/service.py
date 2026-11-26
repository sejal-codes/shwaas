"""Orchestrates one request: validate -> live data -> rule engine -> GenAI explanation."""
from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, Mapping

from app.activity import advise
from app.ai import Assistant
from app.air_data import AirDataProvider, AirReading
from app.aqi import severity, severity_alert
from app.indoor import estimate_indoor_aqi, suggest_fixes
from app.models import ActivityKind, HomeProfile, Plan, Profile, Timing


_HOUSEHOLD_WORDS = {
    Profile.FAMILY_WITH_CHILDREN: "a family with children",
    Profile.ELDERLY: "older adults",
    Profile.ADULT: "adults",
}
_ACTIVITY_WORDS = {
    ActivityKind.SCHOOL_RUN: "taking or collecting a child from school",
    ActivityKind.WORK_COMMUTE: "their own trip to work, college or university",
    ActivityKind.MEDICAL: "a medical visit",
    ActivityKind.ERRAND: "an errand",
    ActivityKind.EXERCISE: "exercise",
    ActivityKind.LEISURE: "a leisure outing or walk",
}


def to_jsonable(value: Any) -> Any:
    """Convert dataclasses, enums and sets into plain JSON-safe values."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = sorted(value, key=str) if isinstance(value, (set, frozenset)) else value
        return [to_jsonable(v) for v in items]
    return value


def _require_mapping(payload: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"'{field}' is required")
    return payload


class AirQualityService:
    def __init__(self, air: AirDataProvider, assistant: Assistant):
        self._air = air
        self._assistant = assistant

    def _context(self, payload: Mapping[str, Any]) -> tuple[HomeProfile, AirReading, str]:
        home = HomeProfile.from_dict(_require_mapping(payload.get("home"), "home"))
        loc = _require_mapping(payload.get("location"), "location")
        location = self._air.resolve(
            city=loc.get("city"),
            latitude=loc.get("latitude"),
            longitude=loc.get("longitude"),
            country=loc.get("country"),
            state=loc.get("state"),
        )
        language = payload.get("language", "en")
        return home, self._air.reading(location), language

    def assess(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        home, reading, language = self._context(payload)
        outdoor = reading.current_aqi
        indoor = estimate_indoor_aqi(outdoor, home)
        fixes = suggest_fixes(outdoor, home)
        facts = {
            "outdoor_aqi": outdoor,
            "outdoor_severity": severity(outdoor).value,
            "indoor_score": indoor.score,
            "indoor_low": indoor.low,
            "indoor_high": indoor.high,
            "household": _HOUSEHOLD_WORDS[home.profile],
            "top_fixes": [{"code": f.code, "points_saved": f.points_saved} for f in fixes],
        }
        explanation = self._assistant.explain(facts, language, kind="assessment")
        return {
            "location": reading.location.name,
            "outdoor": {"aqi": outdoor, "severity": severity(outdoor).value, "alert": severity_alert(outdoor)},
            "indoor": to_jsonable(indoor),
            "fixes": to_jsonable(fixes),
            "explanation": to_jsonable(explanation),
            "estimate_note": "Indoor values are estimates based on your answers, not measurements.",
        }

    def plan_advice(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        home, reading, language = self._context(payload)
        timing = payload.get("timing")
        try:
            timing = Timing(timing)
        except ValueError:
            raise ValueError("'timing' must be 'fixed' or 'flexible'") from None

        structured = payload.get("plan")
        if structured is not None:
            plan = Plan.from_dict({**_require_mapping(structured, "plan"), "timing": timing.value})
        else:
            parsed = self._assistant.parse_plan(payload.get("plan_text"), timing)
            if parsed.status == "needs_clarification":
                return {"status": "needs_clarification", "question": parsed.question}
            if parsed.status == "unavailable":
                return {
                    "status": "unavailable",
                    "message": "The smart plan reader is offline. Please choose your plan from the list.",
                }
            plan = parsed.plan

        advice = advise(
            plan, home, reading.current_aqi, current_hour=reading.current_hour, hourly_aqi=reading.hourly_aqi
        )
        best = advice.travel.recommended if advice.travel else None
        facts = {
            "outdoor_aqi": reading.current_aqi,
            "activity": _ACTIVITY_WORDS[plan.kind],
            "timing": plan.timing.value,
            "household": _HOUSEHOLD_WORDS[home.profile],
            "mask_level": advice.mask.level.value,
            "mask_exposure_reduction_pct": advice.mask.exposure_reduction_pct,
            "recommended_mode": best.mode.value if best else None,
            "co2_saved_vs_car_kg": best.co2_saved_vs_car_kg if best else 0,
            "car_is_fallback": advice.travel.car_is_fallback if advice.travel else False,
            "better_time": to_jsonable(advice.better_time),
            "optional_alternative": advice.optional_alternative,
        }
        explanation = self._assistant.explain(facts, language, kind="plan")
        return {
            "status": "ok",
            "plan": to_jsonable(plan),
            "advice": to_jsonable(advice),
            "explanation": to_jsonable(explanation),
        }

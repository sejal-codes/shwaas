"""Plain-template explanations. Used whenever Gemini is unavailable, so the app never breaks."""
from __future__ import annotations

from typing import Any, Mapping

FIX_TEXT = {
    "close_windows": "keeping windows closed",
    "run_purifier": "running a purifier (or a DIY box-fan filter)",
    "use_kitchen_exhaust": "using the kitchen exhaust while cooking",
    "switch_to_electric_cooking": "cooking on induction or electric",
    "stop_incense": "skipping incense and mosquito coils",
    "stop_indoor_smoking": "not smoking indoors",
    "stop_burning_for_heat": "not burning anything for warmth (use layers and insulation)",
}


def assessment_fallback(facts: Mapping[str, Any]) -> str:
    text = (
        f"Outdoor air is {facts['outdoor_severity'].replace('_', ' ')} (AQI {facts['outdoor_aqi']}). "
        f"We estimate about {facts['indoor_score']} inside your home "
        f"(likely {facts['indoor_low']}-{facts['indoor_high']}). This is an estimate, not a measurement."
    )
    fixes = facts.get("top_fixes") or []
    if fixes:
        best = fixes[0]
        text += (
            f" The biggest improvement is {FIX_TEXT.get(best['code'], best['code'])}, "
            f"worth about {best['points_saved']} points."
        )
    return text


def plan_fallback(facts: Mapping[str, Any]) -> str:
    parts = []
    mask = facts.get("mask_level")
    if mask == "recommended":
        parts.append("Wear a well-fitted N95 for this plan.")
    elif mask == "optional":
        parts.append("An N95 is optional today but helps.")
    mode = facts.get("recommended_mode")
    if mode:
        saved = facts.get("co2_saved_vs_car_kg", 0)
        line = f"Best travel option: {mode.replace('_', ' ')}"
        if saved > 0:
            line += f", which avoids about {saved} kg of CO2 compared with driving alone"
        parts.append(line + ".")
    better = facts.get("better_time")
    if better:
        parts.append(f"If you can, {better['hour']}:00 looks about {better['improvement_pct']}% cleaner.")
    if facts.get("optional_alternative"):
        parts.append("Consider doing this indoors today.")
    parts.append("These are estimates and general guidance, not medical advice.")
    return " ".join(parts)

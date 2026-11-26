"""Runtime settings, read once from environment variables. No secrets live in code."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None = None
    # Tried in order; if one is overloaded the next is used. Override with GEMINI_MODEL="a,b,c".
    gemini_models: tuple[str, ...] = (
        "gemini-flash-lite-latest",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
    )
    openaq_api_key: str | None = None  # optional: real monitor readings from OpenAQ
    measured_radius_m: int = 25_000  # OpenAQ's maximum search radius
    measured_max_age_h: float = 3.0  # older readings are ignored
    http_timeout_s: float = 6.0
    air_cache_ttl_s: int = 600  # live AQI is refreshed at most every 10 minutes
    geocode_cache_ttl_s: int = 86_400
    cache_max_entries: int = 256
    max_plan_chars: int = 300
    rate_limit_per_min: int = 30
    max_request_bytes: int = 16_384

    @classmethod
    def from_env(cls) -> "Settings":
        chosen = tuple(m.strip() for m in (os.environ.get("GEMINI_MODEL") or "").split(",") if m.strip())
        return cls(
            gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
            openaq_api_key=os.environ.get("OPENAQ_API_KEY") or None,
            gemini_models=chosen or cls.gemini_models,
        )

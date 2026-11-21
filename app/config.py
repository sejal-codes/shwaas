"""Runtime settings, read once from environment variables. No secrets live in code."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"
    http_timeout_s: float = 6.0
    air_cache_ttl_s: int = 600  # live AQI is refreshed at most every 10 minutes
    geocode_cache_ttl_s: int = 86_400
    cache_max_entries: int = 256
    max_plan_chars: int = 300
    rate_limit_per_min: int = 30
    max_request_bytes: int = 16_384

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
            gemini_model=os.environ.get("GEMINI_MODEL") or cls.gemini_model,
        )

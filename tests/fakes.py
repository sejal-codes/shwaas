"""Shared test doubles. No test touches the real network."""
from app.config import Settings

SETTINGS = Settings(gemini_api_key="test-key", rate_limit_per_min=1000)

GEOCODE_OK = {"results": [{"name": "Delhi", "latitude": 28.65, "longitude": 77.23}]}


def air_payload(pm25_now=150.0, hourly=None):
    hourly = hourly or {7: 150.0, 11: 80.0, 17: 120.0}
    return {
        "current": {"time": "2026-11-21T07:15", "pm2_5": pm25_now},
        "hourly": {
            "time": [f"2026-11-21T{h:02d}:00" for h in hourly] + ["2026-11-22T11:00"],
            "pm2_5": list(hourly.values()) + [5.0],
        },
    }


class FakeHttp:
    """Stands in for requests: returns canned payloads and counts calls."""

    def __init__(self, geocode=GEOCODE_OK, air=None):
        self.geocode, self.air, self.calls = geocode, air or air_payload(), []

    def __call__(self, url, params, timeout):
        self.calls.append(url)
        return self.geocode if "geocoding" in url else self.air


class FakeGemini:
    """Returns queued replies, or raises if told to."""

    def __init__(self, *replies, error=None):
        self.replies, self.error, self.prompts = list(replies), error, []

    def generate(self, *, system, prompt, json_mode=False, max_tokens=1024):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.replies.pop(0)

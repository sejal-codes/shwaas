"""Builds the JSON the UI tests replay, by calling the REAL API with fake services.
tests/test_fixtures_in_sync.py fails if the API changes shape and the fixtures are not refreshed:
    python -m tests.js_fixtures
"""
import json
from pathlib import Path

from app.ai import Assistant
from app.air_data import AirDataProvider
from app.server import create_app
from app.service import AirQualityService
from tests.fakes import SETTINGS, FakeGemini, FakeHttp

OUT = Path(__file__).parent / "js" / "fixtures"
HOME = {"profile": "family_with_children", "windows": "open", "cooking": "gas"}
LOCATION = {"city": "Delhi"}


def _call(gemini, path, body):
    service = AirQualityService(AirDataProvider(SETTINGS, http_get=FakeHttp()), Assistant(gemini))
    client = create_app(service, SETTINGS).test_client()
    return client.post(path, data=json.dumps(body), content_type="application/json").json


def build() -> dict:
    plan_ok = json.dumps({"status": "ok", "plan": {"kind": "errand", "distance_km": 4}})
    ask = json.dumps({"status": "needs_clarification", "question": "Where are you going?"})
    plan_body = {"home": HOME, "location": LOCATION, "plan_text": "buy vegetables", "timing": "flexible"}
    return {
        "assess": _call(None, "/api/assess", {"home": HOME, "location": LOCATION}),
        "plan_ok": _call(FakeGemini(plan_ok, "Go around 11 and wear an N95."), "/api/plan", plan_body),
        "plan_clarify": _call(FakeGemini(ask), "/api/plan", plan_body),
        "plan_unavailable": _call(None, "/api/plan", plan_body),
        "plan_fixed_school": _call(
            None, "/api/plan",
            {"home": HOME, "location": LOCATION, "timing": "fixed", "plan": {"kind": "school_run", "distance_km": 5}},
        ),
    }


if __name__ == "__main__":
    for name, payload in build().items():
        (OUT / f"{name}.json").write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        print("wrote", name)

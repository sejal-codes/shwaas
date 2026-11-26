import json

import pytest

from app.ai import Assistant
from app.air_data import AirDataProvider
from app.config import Settings
from app.server import create_app
from app.service import AirQualityService
from tests.fakes import SETTINGS, FakeGemini, FakeHttp

HOME = {"profile": "family_with_children", "windows": "open", "cooking": "gas"}
LOCATION = {"city": "Delhi"}


def make_client(gemini=None, settings=SETTINGS, http=None):
    service = AirQualityService(AirDataProvider(settings, http_get=http or FakeHttp()), Assistant(gemini))
    return create_app(service, settings).test_client()


def post(client, path, body):
    return client.post(path, data=json.dumps(body), content_type="application/json")


def test_health():
    assert make_client().get("/api/health").json == {"status": "ok"}


def test_assess_returns_outdoor_indoor_and_fixes():
    res = post(make_client(), "/api/assess", {"home": HOME, "location": LOCATION})
    assert res.status_code == 200
    data = res.json
    assert data["outdoor"]["aqi"] == 324 and data["outdoor"]["alert"]
    assert data["indoor"]["score"] > 0 and 1 <= len(data["fixes"]) <= 3
    assert data["explanation"]["source"] == "template"
    assert "estimate" in data["estimate_note"]


def test_plan_with_gemini_parse_and_flexible_timing():
    reply = json.dumps({"status": "ok", "plan": {"kind": "errand", "distance_km": 2}})
    gemini = FakeGemini(reply, "Go at 11.")
    res = post(make_client(gemini), "/api/plan", {"home": HOME, "location": LOCATION,
                                                     "plan_text": "buy vegetables", "timing": "flexible"})
    assert res.status_code == 200 and res.json["status"] == "ok"
    assert res.json["advice"]["better_time"]["hour"] == 11
    assert res.json["explanation"]["text"] == "Go at 11."


def test_plan_fixed_has_no_timing_advice():
    reply = json.dumps({"status": "ok", "plan": {"kind": "school_run", "distance_km": 3}})
    res = post(make_client(FakeGemini(reply, "ok")), "/api/plan",
               {"home": HOME, "location": LOCATION, "plan_text": "school drop", "timing": "fixed"})
    assert res.json["advice"]["better_time"] is None
    assert res.json["advice"]["optional_alternative"] is None


def test_plan_structured_fallback_works_without_gemini():
    res = post(make_client(), "/api/plan", {"home": HOME, "location": LOCATION, "timing": "fixed",
                                             "plan": {"kind": "work_commute", "distance_km": 6}})
    assert res.json["status"] == "ok" and res.json["explanation"]["source"] == "template"


def test_plan_text_without_gemini_is_reported_unavailable():
    res = post(make_client(), "/api/plan", {"home": HOME, "location": LOCATION,
                                             "plan_text": "school", "timing": "fixed"})
    assert res.json["status"] == "unavailable"


def test_vague_plan_returns_one_question():
    reply = json.dumps({"status": "needs_clarification", "question": "Where to?"})
    res = post(make_client(FakeGemini(reply)), "/api/plan",
               {"home": HOME, "location": LOCATION, "plan_text": "going out", "timing": "fixed"})
    assert res.json == {"status": "needs_clarification", "question": "Where to?"}


@pytest.mark.parametrize("body", [
    {"home": {"profile": "x"}, "location": LOCATION},
    {"home": HOME, "location": {"city": "<b>"}},
    {"home": HOME},
    {},
])
def test_assess_rejects_bad_input_with_400(body):
    res = post(make_client(), "/api/assess", body)
    assert res.status_code == 400 and "error" in res.json


def test_plan_rejects_bad_timing():
    res = post(make_client(), "/api/plan", {"home": HOME, "location": LOCATION, "timing": "whenever",
                                             "plan": {"kind": "errand", "distance_km": 1}})
    assert res.status_code == 400


def test_non_json_body_is_rejected():
    res = make_client().post("/api/assess", data="hello", content_type="text/plain")
    assert res.status_code == 400


def test_oversized_body_is_rejected():
    tiny = Settings(gemini_api_key="k", max_request_bytes=50, rate_limit_per_min=1000)
    res = post(make_client(settings=tiny), "/api/assess", {"home": HOME, "location": LOCATION})
    assert res.status_code == 413


def test_rate_limit_kicks_in():
    strict = Settings(gemini_api_key="k", rate_limit_per_min=2)
    client = make_client(settings=strict)
    codes = [client.get("/api/health").status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_security_headers_and_no_store():
    res = make_client().get("/api/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in res.headers["Content-Security-Policy"]
    assert res.headers["Cache-Control"] == "no-store"


def test_unknown_route_is_json_404_not_a_stack_trace():
    res = make_client().get("/nope")
    assert res.status_code == 404 and "error" in res.json


def test_air_provider_failure_becomes_502_without_leaking_details():
    from app.air_data import AirDataError

    def boom(url, params, timeout):
        raise AirDataError("Live air data is unavailable right now. Please try again shortly.")

    res = post(make_client(http=boom), "/api/assess", {"home": HOME, "location": LOCATION})
    assert res.status_code == 502 and "unavailable" in res.json["error"]


# ---- web UI is served safely
def test_home_page_is_served_with_security_headers():
    res = make_client().get("/")
    assert res.status_code == 200 and res.mimetype == "text/html"
    assert b"<h1" in res.data
    assert "default-src 'self'" in res.headers["Content-Security-Policy"]


@pytest.mark.parametrize("path, mime", [
    ("/static/app.js", "text/javascript"), ("/static/styles.css", "text/css"),
    ("/static/i18n.json", "application/json"), ("/static/render.js", "text/javascript"),
])
def test_static_files_are_served(path, mime):
    res = make_client().get(path)
    assert res.status_code == 200 and res.mimetype == mime


def test_ai_is_given_plain_words_not_internal_codes():
    reply = json.dumps({"status": "ok", "plan": {"kind": "work_commute", "distance_km": 5}})
    gemini = FakeGemini(reply, "Plain advice.")
    post(make_client(gemini), "/api/plan", {"home": HOME, "location": LOCATION, "timing": "fixed", "plan_text": "college trip"})
    explain_prompt = gemini.prompts[1]
    assert "family with children" in explain_prompt and "college" in explain_prompt
    assert "work_commute" not in explain_prompt and "family_with_children" not in explain_prompt


def test_assessment_prompt_uses_plain_words_too():
    gemini = FakeGemini("Fine.")
    post(make_client(gemini), "/api/assess", {"home": HOME, "location": LOCATION})
    assert "family_with_children" not in gemini.prompts[0]


def test_explanation_prompt_forbids_greetings_and_missing_info_remarks():
    from app.ai import _EXPLAIN_SYSTEM
    assert "no greeting" in _EXPLAIN_SYSTEM and "Never mention missing" in _EXPLAIN_SYSTEM


def test_assess_accepts_a_location_picked_on_the_map():
    http = FakeHttp()
    res = post(make_client(http=http), "/api/assess",
               {"home": HOME, "location": {"country": "India", "state": "Karnataka", "latitude": 14.52, "longitude": 75.72}})
    assert res.status_code == 200 and res.json["location"] == "Karnataka, India"
    assert http.calls and all("geocoding" not in url for url in http.calls), "no city lookup for a map pick"


@pytest.mark.parametrize("location", [
    {"country": "<b>", "state": "X", "latitude": 1, "longitude": 2},
    {"country": "India", "state": "K" * 90, "latitude": 1, "longitude": 2},
    {"country": "India", "state": "Karnataka"},
    {"state": "Karnataka", "latitude": 1, "longitude": 2},
    {"country": "India", "latitude": 99, "longitude": 2},
])
def test_bad_map_locations_are_rejected_with_400(location):
    res = post(make_client(), "/api/assess", {"home": HOME, "location": location})
    assert res.status_code == 400 and "error" in res.json

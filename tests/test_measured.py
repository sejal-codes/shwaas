from datetime import datetime, timedelta, timezone

import pytest
import requests

from app.air_data import AirDataProvider, Location
from app.aqi import naqi_to_pm25, pm25_to_naqi
from app.config import Settings
from app.measured import MeasuredProvider, haversine_km
from tests.fakes import FakeHttp

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
KEY = Settings(openaq_api_key="k", rate_limit_per_min=1000)


def station(sid, name, lat, lon, sensor=11, parameter="pm25"):
    return {"id": sid, "name": name, "coordinates": {"latitude": lat, "longitude": lon},
            "sensors": [{"id": sensor, "parameter": {"id": 2 if parameter == "pm25" else 9, "name": parameter}}]}


def latest(sensor, value, hours_ago=0.5):
    stamp = (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"results": [{"sensorsId": sensor, "value": value, "datetime": {"utc": stamp}}]}


class Scripted:
    def __init__(self, listing, readings):
        self.listing, self.readings, self.calls = listing, readings, []

    def __call__(self, url, params, headers, timeout):
        self.calls.append((url, params, headers))
        if url.endswith("/locations"):
            if isinstance(self.listing, Exception):
                raise self.listing
            return {"results": self.listing}
        return self.readings[int(url.rsplit("/", 2)[1])]


def provider(http, settings=KEY):
    return MeasuredProvider(settings, http_get=http, now=lambda: NOW)


def test_without_a_key_nothing_is_asked():
    http = Scripted([], {})
    assert provider(http, Settings()).nearest_pm25(12.9, 77.6) is None and http.calls == []


def test_the_nearest_fresh_station_wins_and_the_key_is_sent_as_a_header():
    http = Scripted([station(2, "Far", 13.5, 77.6), station(1, "Near", 12.95, 77.6)],
                    {1: latest(11, 41.26), 2: latest(11, 5.0)})
    found = provider(http).nearest_pm25(12.9, 77.6)
    assert (found.station, found.pm25) == ("Near", 41.3) and 0 < found.distance_km < 10
    url, params, headers = http.calls[0]
    assert headers == {"X-API-Key": "k"} and params["coordinates"] == "12.9,77.6" and params["radius"] == 25000


def test_stale_readings_are_skipped_in_favour_of_the_next_station():
    http = Scripted([station(1, "Stale", 12.91, 77.6), station(2, "Fresh", 13.0, 77.6)],
                    {1: latest(11, 30, hours_ago=9), 2: latest(11, 22)})
    assert provider(http).nearest_pm25(12.9, 77.6).station == "Fresh"


@pytest.mark.parametrize("value", [-3, 5000, "12", None, True])
def test_absurd_values_are_ignored(value):
    http = Scripted([station(1, "Odd", 12.91, 77.6)], {1: latest(11, value)})
    assert provider(http).nearest_pm25(12.9, 77.6) is None


def test_only_the_pm25_sensor_counts():
    http = Scripted([station(1, "Ozone only", 12.91, 77.6, parameter="o3")], {1: latest(11, 20)})
    assert provider(http).nearest_pm25(12.9, 77.6) is None
    other = {"results": [{"sensorsId": 99, "value": 20, "datetime": {"utc": (NOW - timedelta(minutes=5)).isoformat()}}]}
    assert provider(Scripted([station(1, "S", 12.91, 77.6)], {1: other})).nearest_pm25(12.9, 77.6) is None


def test_failures_fall_back_quietly_and_are_retried_later():
    http = Scripted(requests.ConnectionError("down"), {})
    p = provider(http)
    assert p.nearest_pm25(12.9, 77.6) is None and p.nearest_pm25(12.9, 77.6) is None
    assert len(http.calls) == 2, "a failure is not cached"


def test_no_station_nearby_is_remembered():
    http = Scripted([], {})
    p = provider(http)
    assert p.nearest_pm25(12.9, 77.6) is None and p.nearest_pm25(12.9, 77.6) is None
    assert len(http.calls) == 1


def test_air_provider_prefers_a_measurement_but_keeps_the_model_forecast():
    measured = provider(Scripted([station(1, "Hebbal", 12.91, 77.6)], {1: latest(11, 45.0)}))
    reading = AirDataProvider(Settings(), http_get=FakeHttp(), measured=measured).reading(Location("X", 12.9, 77.6))
    assert reading.source == "measured" and reading.station == "Hebbal" and reading.pm25 == 45.0
    assert reading.current_aqi == pm25_to_naqi(45.0) and reading.hourly_aqi, "forecast still comes from the model"


def test_air_provider_without_a_station_says_it_is_a_model_estimate():
    reading = AirDataProvider(Settings(), http_get=FakeHttp(), measured=provider(Scripted([], {}))).reading(Location("X", 12.9, 77.6))
    assert reading.source == "model" and reading.station is None and reading.pm25 == 150.0


def test_conversion_to_units_round_trips():
    for pm in (0, 4.2, 12, 30, 45, 90, 150, 300):
        assert abs(naqi_to_pm25(pm25_to_naqi(pm)) - pm) <= 1.5, pm
    assert naqi_to_pm25(14) == 8.4 and naqi_to_pm25(500) == 380.0


def test_haversine_is_sane():
    assert haversine_km(12.97, 77.59, 12.97, 77.59) == 0
    assert 1700 < haversine_km(28.65, 77.23, 12.97, 77.59) < 1800  # Delhi to Bengaluru


def test_api_exposes_units_and_where_the_number_came_from():
    import json
    from tests.test_server import HOME, LOCATION, make_client
    res = make_client().post("/api/assess", data=json.dumps({"home": HOME, "location": LOCATION}), content_type="application/json")
    out = res.json["outdoor"]
    assert out["scale"] == "india_naqi" and out["source"] == "model" and out["pm25"] == 150.0
    assert res.json["indoor"]["pm25"] > 0


def test_settings_read_the_openaq_key(monkeypatch):
    monkeypatch.setenv("OPENAQ_API_KEY", "abc")
    assert Settings.from_env().openaq_api_key == "abc"
    monkeypatch.delenv("OPENAQ_API_KEY")
    assert Settings.from_env().openaq_api_key is None

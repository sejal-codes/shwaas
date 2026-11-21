import pytest

from app.air_data import (AirDataError, AirDataProvider, Location, parse_air, parse_geocode,
                          validate_city, validate_coordinates)
from tests.fakes import SETTINGS, FakeHttp, air_payload

LOC = Location("Delhi", 28.65, 77.23)


def test_parse_air_converts_pm25_and_keeps_today_only():
    reading = parse_air(air_payload(pm25_now=150), LOC)
    assert reading.current_hour == 7
    assert reading.current_aqi == 324  # PM2.5 150 -> NAQI band 120-250
    assert 11 in reading.hourly_aqi and len(reading.hourly_aqi) == 3  # tomorrow's hour dropped


def test_parse_air_skips_missing_values():
    payload = air_payload()
    payload["hourly"]["pm2_5"][1] = None
    assert 11 not in parse_air(payload, LOC).hourly_aqi


@pytest.mark.parametrize("payload", [{}, {"current": {}}, {"current": {"time": "x", "pm2_5": 1}, "hourly": {}}])
def test_parse_air_rejects_bad_payloads(payload):
    with pytest.raises(AirDataError):
        parse_air(payload, LOC)


def test_parse_geocode_not_found():
    with pytest.raises(AirDataError):
        parse_geocode({})


@pytest.mark.parametrize("bad", ["", "a", "12345", "x" * 81, None, 5, "<script>alert(1)</script>"])
def test_city_validation_rejects(bad):
    with pytest.raises(ValueError):
        validate_city(bad)


def test_city_validation_accepts_real_names():
    assert validate_city("  New   Delhi ") == "New Delhi"
    assert validate_city("बेंगलुरु") == "बेंगलुरु"
    assert validate_city("ಬೆಂಗಳೂರು")
    assert validate_city("St. John's")


@pytest.mark.parametrize("lat, lon", [(91, 0), (0, 181), ("1", 2), (True, 2), (None, None)])
def test_coordinate_validation_rejects(lat, lon):
    with pytest.raises(ValueError):
        validate_coordinates(lat, lon)


def test_provider_caches_lookups():
    http = FakeHttp()
    provider = AirDataProvider(SETTINGS, http_get=http)
    loc = provider.resolve(city="Delhi")
    provider.resolve(city="delhi")
    provider.reading(loc)
    provider.reading(loc)
    assert len(http.calls) == 2  # one geocode + one air call, everything else cached


def test_provider_uses_coordinates_directly():
    http = FakeHttp()
    loc = AirDataProvider(SETTINGS, http_get=http).resolve(latitude=12.9, longitude=77.6)
    assert loc.latitude == 12.9 and http.calls == []

"""Live air data from Open-Meteo (free, no API key): geocoding + current/hourly PM2.5.

Parsing is separated from HTTP so it can be unit tested without the network.
"""
from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import requests

from app.aqi import pm25_to_naqi
from app.cache import TTLCache
from app.config import Settings

log = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
_CITY_PUNCTUATION = frozenset(" .,'’-")


class AirDataError(Exception):
    """Raised with a user-safe message when air data cannot be obtained."""


@dataclass(frozen=True)
class Location:
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class AirReading:
    location: Location
    current_aqi: int
    current_hour: int
    hourly_aqi: dict[int, int]  # hour of day (local) -> NAQI, today only


# ---------------------------------------------------------------- validation
def validate_city(city: Any) -> str:
    """Letters from any script (incl. combining marks used in Hindi/Kannada) plus . , ' - and spaces."""
    error = ValueError("Enter a city name (2-80 letters).")
    if not isinstance(city, str):
        raise error
    cleaned = " ".join(city.split())
    allowed = all(
        unicodedata.category(ch)[0] in "LM" or ch in _CITY_PUNCTUATION for ch in cleaned
    )
    if not (2 <= len(cleaned) <= 80) or not allowed or unicodedata.category(cleaned[0])[0] != "L":
        raise error
    return cleaned


def validate_place_name(name: Any, field: str) -> str:
    """Country or state names from the map: letters, marks, digits and a little punctuation, up to 80 chars."""
    error = ValueError(f"'{field}' must be a place name (up to 80 characters).")
    if not isinstance(name, str):
        raise error
    cleaned = " ".join(name.split())
    allowed = all(
        unicodedata.category(ch)[0] in "LMN" or ch in _CITY_PUNCTUATION or ch in "()/&" for ch in cleaned
    )
    if not (1 <= len(cleaned) <= 80) or not allowed or unicodedata.category(cleaned[0])[0] not in "LN":
        raise error
    return cleaned


def validate_coordinates(latitude: Any, longitude: Any) -> tuple[float, float]:
    for value in (latitude, longitude):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Coordinates must be numbers.")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Coordinates are out of range.")
    return float(latitude), float(longitude)


# ------------------------------------------------------------------- parsing
def parse_geocode(payload: Mapping[str, Any]) -> Location:
    results = payload.get("results") or []
    if not results:
        raise AirDataError("We could not find that place. Try a nearby city.")
    try:
        first = results[0]
        return Location(str(first["name"]), float(first["latitude"]), float(first["longitude"]))
    except (KeyError, TypeError, ValueError):
        raise AirDataError("The location service returned an unexpected response.") from None


def parse_air(payload: Mapping[str, Any], location: Location) -> AirReading:
    try:
        current = payload["current"]
        today = current["time"][:10]
        current_hour = int(current["time"][11:13])
        current_aqi = pm25_to_naqi(float(current["pm2_5"]))
        hourly: dict[int, int] = {}
        for stamp, pm25 in zip(payload["hourly"]["time"], payload["hourly"]["pm2_5"]):
            if pm25 is not None and stamp[:10] == today:
                hourly[int(stamp[11:13])] = pm25_to_naqi(float(pm25))
    except (KeyError, TypeError, ValueError, IndexError):
        raise AirDataError("The air-quality service returned an unexpected response.") from None
    return AirReading(location, current_aqi, current_hour, hourly)


# ------------------------------------------------------------------- network
def _get_json(url: str, params: Mapping[str, Any], timeout: float) -> Mapping[str, Any]:
    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as err:
        status = getattr(getattr(err, "response", None), "status_code", "")
        log.warning("Air data request to %s failed: %s %s", url, type(err).__name__, status)
        raise AirDataError("Live air data is unavailable right now. Please try again shortly.") from None
    if not isinstance(data, dict):
        raise AirDataError("The air-quality service returned an unexpected response.")
    return data


def _place_label(country: Any, state: Any) -> str:
    """'State, Country' for a place picked on the map; otherwise a neutral label for device coordinates."""
    if state is not None and country is None:
        raise ValueError("'country' is required when 'state' is given.")
    if country is None:
        return "Your location"
    name = validate_place_name(country, "country")
    if state is None:
        return name
    return f"{validate_place_name(state, 'state')}, {name}"


class AirDataProvider:
    def __init__(self, settings: Settings, http_get: Callable[..., Mapping[str, Any]] = _get_json):
        self._timeout = settings.http_timeout_s
        self._http_get = http_get
        self._geo_cache = TTLCache(settings.geocode_cache_ttl_s, settings.cache_max_entries)
        self._air_cache = TTLCache(settings.air_cache_ttl_s, settings.cache_max_entries)

    def resolve(
        self,
        *,
        city: Any = None,
        latitude: Any = None,
        longitude: Any = None,
        country: Any = None,
        state: Any = None,
    ) -> Location:
        if city is not None:
            name = validate_city(city)
            key = name.lower()
            cached = self._geo_cache.get(key)
            if cached is None:
                payload = self._http_get(
                    GEOCODE_URL, {"name": name, "count": 1, "language": "en", "format": "json"}, self._timeout
                )
                cached = parse_geocode(payload)
                self._geo_cache.set(key, cached)
            return cached
        lat, lon = validate_coordinates(latitude, longitude)
        return Location(_place_label(country, state), lat, lon)

    def reading(self, location: Location) -> AirReading:
        key = (round(location.latitude, 2), round(location.longitude, 2))
        cached = self._air_cache.get(key)
        if cached is not None:
            return AirReading(location, cached.current_aqi, cached.current_hour, cached.hourly_aqi)
        payload = self._http_get(
            AIR_URL,
            {
                "latitude": location.latitude,
                "longitude": location.longitude,
                "current": "pm2_5",
                "hourly": "pm2_5",
                "forecast_days": 1,
                "timezone": "auto",
            },
            self._timeout,
        )
        reading = parse_air(payload, location)
        self._air_cache.set(key, reading)
        return reading

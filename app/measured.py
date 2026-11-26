"""Real, measured PM2.5 from the nearest monitoring station, via OpenAQ (needs a free API key).

OpenAQ gathers readings from government and research monitors worldwide. Where no recent reading exists within 25 km
(common in deserts and many countries), this returns None and the app falls back to the model estimate and says so.
Every failure is non-fatal on purpose: the app must keep working without this.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

import requests

from app.cache import TTLCache
from app.config import Settings

log = logging.getLogger(__name__)

LOCATIONS_URL = "https://api.openaq.org/v3/locations"
LATEST_URL = "https://api.openaq.org/v3/locations/{id}/latest"
PM25_PARAMETER_ID = 2
MAX_CANDIDATES = 4  # nearest stations to try, so one request costs at most 5 calls


@dataclass(frozen=True)
class Measurement:
    pm25: float  # ug/m3
    station: str
    distance_km: float
    observed: str  # ISO-8601 UTC time of the reading


def _get(url: str, params: Mapping[str, Any], headers: Mapping[str, str], timeout: float) -> Mapping[str, Any]:
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as err:
        status = getattr(getattr(err, "response", None), "status_code", "")
        log.warning("OpenAQ request failed: %s %s", type(err).__name__, status)
        raise
    if not isinstance(data, dict):
        raise ValueError("unexpected OpenAQ response")
    return data


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _pm25_sensor_id(location: Mapping[str, Any]) -> int | None:
    for sensor in location.get("sensors") or []:
        parameter = sensor.get("parameter") or {}
        name = str(parameter.get("name", "")).lower()
        if parameter.get("id") == PM25_PARAMETER_ID or name in ("pm25", "pm2.5"):
            return sensor.get("id")
    return None


class MeasuredProvider:
    def __init__(
        self,
        settings: Settings,
        http_get: Callable[..., Mapping[str, Any]] = _get,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self._key = settings.openaq_api_key
        self._radius = settings.measured_radius_m
        self._max_age = timedelta(hours=settings.measured_max_age_h)
        self._timeout = settings.http_timeout_s
        self._http_get, self._now = http_get, now
        self._cache = TTLCache(settings.air_cache_ttl_s, settings.cache_max_entries)

    @property
    def enabled(self) -> bool:
        return bool(self._key)

    def nearest_pm25(self, latitude: float, longitude: float) -> Measurement | None:
        if not self._key:
            return None
        cache_key = (round(latitude, 2), round(longitude, 2))
        if cache_key in self._cache._data:  # a cached "nothing nearby" is worth remembering too
            return self._cache.get(cache_key)
        try:
            found = self._lookup(latitude, longitude)
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
            return None  # not cached: try again next time
        self._cache.set(cache_key, found)
        return found

    def _lookup(self, latitude: float, longitude: float) -> Measurement | None:
        headers = {"X-API-Key": self._key}
        listing = self._http_get(
            LOCATIONS_URL,
            {"coordinates": f"{latitude},{longitude}", "radius": self._radius, "parameters_id": PM25_PARAMETER_ID, "limit": 25},
            headers,
            self._timeout,
        )
        stations = []
        for location in listing.get("results") or []:
            sensor_id, coords = _pm25_sensor_id(location), location.get("coordinates") or {}
            if sensor_id is None or "latitude" not in coords or "longitude" not in coords:
                continue
            distance = haversine_km(latitude, longitude, float(coords["latitude"]), float(coords["longitude"]))
            stations.append((distance, location, sensor_id))
        stations.sort(key=lambda item: item[0])

        for distance, location, sensor_id in stations[:MAX_CANDIDATES]:
            latest = self._http_get(LATEST_URL.format(id=int(location["id"])), {"limit": 100}, headers, self._timeout)
            for reading in latest.get("results") or []:
                if reading.get("sensorsId") != sensor_id:
                    continue
                value = reading.get("value")
                moment = _parse_time((reading.get("datetime") or {}).get("utc"))
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1000 or moment is None:
                    continue
                if self._now() - moment > self._max_age:
                    continue  # too old to call "now"
                name = " ".join(str(location.get("name") or "a nearby station").split())[:60]
                return Measurement(round(float(value), 1), name, round(distance, 1), moment.astimezone(timezone.utc).isoformat())
        return None

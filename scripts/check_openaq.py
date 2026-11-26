"""Developer tool: see what real monitors OpenAQ has near a place.

    python -m scripts.check_openaq 14.37 75.67
Needs OPENAQ_API_KEY (free: explore.openaq.org/register).
"""
import sys

from app.config import Settings
from app.measured import LATEST_URL, LOCATIONS_URL, PM25_PARAMETER_ID, MeasuredProvider, _get, haversine_km


def main(argv: list[str]) -> int:
    settings = Settings.from_env()
    if not settings.openaq_api_key:
        print("OPENAQ_API_KEY is not set in this terminal. Get a free key at explore.openaq.org/register.")
        return 1
    lat, lon = (float(argv[0]), float(argv[1])) if len(argv) >= 2 else (28.65, 77.23)
    headers = {"X-API-Key": settings.openaq_api_key}
    listing = _get(LOCATIONS_URL, {"coordinates": f"{lat},{lon}", "radius": settings.measured_radius_m,
                                   "parameters_id": PM25_PARAMETER_ID, "limit": 25}, headers, 10)
    results = listing.get("results") or []
    print(f"{len(results)} stations with PM2.5 within {settings.measured_radius_m // 1000} km of {lat}, {lon}")
    for item in results[:6]:
        c = item.get("coordinates") or {}
        km = haversine_km(lat, lon, c.get("latitude", lat), c.get("longitude", lon))
        print(f"  {km:5.1f} km  {item.get('name')}  (monitor: {item.get('isMonitor')})")
    found = MeasuredProvider(settings).nearest_pm25(lat, lon)
    print("\nWhat the app would use:", found or "nothing recent nearby, so it falls back to the model estimate")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

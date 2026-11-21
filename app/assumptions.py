"""Every tunable number in one place.

These are rough, transparent estimates (not measurements). Keeping them here makes
them easy to review, change and explain in the README. Nothing in the rules is
hard-coded elsewhere.
"""
from app.models import CookingFuel, Heating, TravelMode, WindowHabit

# ------------------------------------------------------------- indoor air
# Share of outdoor air that gets inside, by window habit.
INFILTRATION = {
    WindowHabit.OPEN: 0.9,
    WindowHabit.SOMETIMES: 0.7,
    WindowHabit.CLOSED: 0.5,
}
# Extra indoor pollution from sources, in AQI points.
COOKING_SOURCE_POINTS = {
    CookingFuel.ELECTRIC: 0,
    CookingFuel.GAS: 25,
    CookingFuel.BIOMASS: 70,
}
HEATING_SOURCE_POINTS = {Heating.NONE: 0, Heating.ELECTRIC: 0, Heating.COMBUSTION: 40}
INCENSE_POINTS = 20
SMOKING_POINTS = 50
EXHAUST_REDUCTION = 0.5  # share of cooking pollution removed by a kitchen exhaust
PURIFIER_REDUCTION = 0.5  # share of indoor pollution removed by a purifier / DIY filter
ESTIMATE_UNCERTAINTY = 0.25  # +/- band shown around the indoor estimate
MAX_FIXES = 3

# ------------------------------------------------------------------ travel
MODE_SPEED_KMH = {
    TravelMode.WALK: 5,
    TravelMode.CYCLE: 14,
    TravelMode.TWO_WHEELER: 25,
    TravelMode.E_RICKSHAW: 18,
    TravelMode.METRO_BUS: 20,
    TravelMode.CARPOOL: 20,
    TravelMode.PRIVATE_CAR: 20,
}
# Relative pollution breathed per minute (walking = 1.0). Faster breathing while
# cycling raises it; closed vehicles with recirculation lower it.
MODE_EXPOSURE_FACTOR = {
    TravelMode.WALK: 1.0,
    TravelMode.CYCLE: 1.3,
    TravelMode.TWO_WHEELER: 1.0,
    TravelMode.E_RICKSHAW: 0.8,
    TravelMode.METRO_BUS: 0.6,
    TravelMode.CARPOOL: 0.45,
    TravelMode.PRIVATE_CAR: 0.4,
}
# Open-air minutes spent walking to a stop or station.
MODE_ACCESS_MINUTES = {TravelMode.METRO_BUS: 10}
# Rough grams of CO2 per passenger-km. Illustrative defaults - replace with
# sourced values for your region if you have them.
MODE_CO2_G_PER_KM = {
    TravelMode.WALK: 0,
    TravelMode.CYCLE: 0,
    TravelMode.TWO_WHEELER: 35,
    TravelMode.E_RICKSHAW: 15,
    TravelMode.METRO_BUS: 30,
    TravelMode.CARPOOL: 45,
    TravelMode.PRIVATE_CAR: 170,
}
OPEN_AIR_MODES = frozenset(
    {TravelMode.WALK, TravelMode.CYCLE, TravelMode.TWO_WHEELER, TravelMode.E_RICKSHAW}
)
SHORT_TRIP_KM = 1.0  # short enough to do in the open with a mask
MAX_WALK_KM = {"adult": 2.0, "vulnerable": 1.0}
MAX_CYCLE_KM = 6.0
# AQI at or above which open-air travel is avoided when a safer option exists.
OPEN_AIR_AVOID_AQI = {"adult": 400, "vulnerable": 300}

# -------------------------------------------------------------------- mask
MASK_OPTIONAL_AQI = 100  # above this an N95 is optional for healthy adults
MASK_RECOMMENDED_AQI = 200  # above this an N95 is recommended for everyone
N95_PENETRATION = 0.3  # share of pollution still reaching you with a well-fitted N95

# ------------------------------------------------------------------ timing
CLEAN_HOURS = range(6, 22)  # only suggest daytime slots
MIN_TIMING_IMPROVEMENT = 0.10  # ignore gains smaller than 10%

# ------------------------------------------------------------------ alerts
ALERT_AQI = 300

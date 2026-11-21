import pytest

from app.models import ActivityKind, Plan, Profile, Timing, TravelMode as M
from app.travel import rank_modes


def trip(km, modes=None):
    kwargs = {"available_modes": frozenset(modes)} if modes else {}
    return Plan(ActivityKind.SCHOOL_RUN, Timing.FIXED, distance_km=km, **kwargs)


def test_cleanest_safe_option_wins_for_adult_on_a_normal_day():
    rec = rank_modes(trip(1.5), Profile.ADULT, 150)
    assert rec.recommended.mode in (M.WALK, M.CYCLE)


def test_private_car_is_not_chosen_when_cleaner_options_exist():
    rec = rank_modes(trip(8), Profile.ADULT, 250)
    assert rec.recommended.mode is not M.PRIVATE_CAR
    assert not rec.car_is_fallback


def test_car_is_a_flagged_fallback_when_it_is_the_only_option():
    rec = rank_modes(trip(8, {M.PRIVATE_CAR}), Profile.FAMILY_WITH_CHILDREN, 400)
    assert rec.recommended.mode is M.PRIVATE_CAR
    assert rec.car_is_fallback


def test_open_air_modes_avoided_for_vulnerable_in_very_poor_air():
    rec = rank_modes(trip(5), Profile.FAMILY_WITH_CHILDREN, 350)
    modes = {o.mode for o in rec.options}
    assert modes.isdisjoint({M.WALK, M.CYCLE, M.TWO_WHEELER, M.E_RICKSHAW})


def test_short_trip_allows_walking_even_in_bad_air():
    rec = rank_modes(trip(0.8), Profile.FAMILY_WITH_CHILDREN, 380)
    assert M.WALK in {o.mode for o in rec.options}


def test_elderly_are_never_sent_cycling():
    rec = rank_modes(trip(3), Profile.ELDERLY, 120)
    assert M.CYCLE not in {o.mode for o in rec.options}


def test_walking_too_far_is_not_offered():
    rec = rank_modes(trip(6), Profile.ADULT, 100)
    assert M.WALK not in {o.mode for o in rec.options}


def test_co2_saved_vs_car_is_positive_for_cleaner_modes():
    rec = rank_modes(trip(10), Profile.ADULT, 200)
    metro = next(o for o in rec.options if o.mode is M.METRO_BUS)
    assert metro.co2_saved_vs_car_kg > 0
    car = next(o for o in rec.options if o.mode is M.PRIVATE_CAR)
    assert car.co2_saved_vs_car_kg == 0


def test_closed_vehicles_cut_exposure():
    rec = rank_modes(trip(6, {M.TWO_WHEELER, M.PRIVATE_CAR}), Profile.ADULT, 200)
    by_mode = {o.mode: o for o in rec.options}
    assert by_mode[M.PRIVATE_CAR].exposure_aqi_hours < by_mode[M.TWO_WHEELER].exposure_aqi_hours


def test_when_nothing_is_safe_we_still_return_options_and_flag_it():
    rec = rank_modes(trip(5, {M.TWO_WHEELER}), Profile.ADULT, 450)
    assert rec.no_safe_option
    assert rec.recommended.mode is M.TWO_WHEELER


@pytest.mark.parametrize("aqi", [-1, float("nan")])
def test_bad_aqi_rejected(aqi):
    with pytest.raises(ValueError):
        rank_modes(trip(3), Profile.ADULT, aqi)

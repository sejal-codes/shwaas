from dataclasses import replace

import pytest

from app.indoor import estimate_indoor_aqi, suggest_fixes
from app.models import CookingFuel, Heating, WindowHabit


def test_closed_windows_lower_the_estimate(home):
    open_home = estimate_indoor_aqi(380, home)
    closed_home = estimate_indoor_aqi(380, replace(home, windows=WindowHabit.CLOSED))
    assert closed_home.score < open_home.score


def test_purifier_lowers_the_estimate(home):
    assert (
        estimate_indoor_aqi(380, replace(home, has_purifier=True)).score
        < estimate_indoor_aqi(380, home).score
    )


def test_exhaust_only_helps_when_cooking_makes_smoke(home):
    electric = replace(home, cooking=CookingFuel.ELECTRIC)
    assert (
        estimate_indoor_aqi(100, replace(electric, has_kitchen_exhaust=True)).score
        == estimate_indoor_aqi(100, electric).score
    )
    assert (
        estimate_indoor_aqi(100, replace(home, has_kitchen_exhaust=True)).score
        < estimate_indoor_aqi(100, home).score
    )


def test_known_value(home):
    # open windows (0.9) on 400 -> 360, plus gas cooking 25 -> 385
    assert estimate_indoor_aqi(400, home).score == 385


def test_range_brackets_score_and_stays_in_scale(home):
    est = estimate_indoor_aqi(480, home)
    assert est.low <= est.score <= est.high <= 500


def test_estimate_never_exceeds_scale(home):
    worst = replace(home, cooking=CookingFuel.BIOMASS, heating=Heating.COMBUSTION,
                    burns_incense=True, indoor_smoking=True)
    assert estimate_indoor_aqi(500, worst).score == 500


def test_factors_explain_the_result(home):
    codes = {f.code for f in estimate_indoor_aqi(300, home).factors}
    assert {"windows_open", "cooking_gas"} <= codes


def test_input_is_not_mutated(home):
    before = replace(home)
    estimate_indoor_aqi(300, home)
    suggest_fixes(300, home)
    assert home == before


def test_fixes_are_ranked_by_real_impact(home):
    fixes = suggest_fixes(380, home)
    assert 0 < len(fixes) <= 3
    saved = [f.points_saved for f in fixes]
    assert saved == sorted(saved, reverse=True)
    assert all(f.points_saved > 0 for f in fixes)


def test_no_fix_for_something_already_done():
    from app.models import HomeProfile, Profile
    tidy = HomeProfile(Profile.ADULT, WindowHabit.CLOSED, CookingFuel.ELECTRIC,
                       has_purifier=True)
    assert suggest_fixes(300, tidy) == ()


@pytest.mark.parametrize("bad", [-5, float("nan"), "300"])
def test_bad_outdoor_aqi_rejected(home, bad):
    with pytest.raises(ValueError):
        estimate_indoor_aqi(bad, home)

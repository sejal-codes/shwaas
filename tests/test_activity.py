import pytest

from app.activity import MaskLevel, advise
from app.models import ActivityKind as K, Plan, Profile, Timing

HOURLY = {7: 410, 11: 290}


def plan(kind, timing=Timing.FIXED, km=3.0):
    return Plan(kind, timing, distance_km=km)


def test_essential_activities_never_get_a_skip_or_indoor_suggestion(home):
    for kind in (K.SCHOOL_RUN, K.WORK_COMMUTE, K.MEDICAL):
        advice = advise(plan(kind), home, 450)
        assert advice.optional_alternative is None


def test_optional_exercise_gets_indoor_alternative_in_bad_air(home):
    advice = advise(plan(K.EXERCISE, km=0), home, 320)
    assert advice.optional_alternative is not None


def test_optional_exercise_in_clean_air_gets_nothing(home):
    assert advise(plan(K.EXERCISE, km=0), home, 60).optional_alternative is None


def test_timing_advice_only_when_flexible(home):
    fixed = advise(plan(K.ERRAND), home, 410, current_hour=7, hourly_aqi=HOURLY)
    flexible = advise(plan(K.ERRAND, Timing.FLEXIBLE), home, 410, current_hour=7, hourly_aqi=HOURLY)
    assert fixed.better_time is None
    assert flexible.better_time.hour == 11


def test_flexible_without_forecast_is_safe(home):
    assert advise(plan(K.ERRAND, Timing.FLEXIBLE), home, 410).better_time is None


@pytest.mark.parametrize(
    "aqi, profile, level",
    [
        (80, Profile.ADULT, MaskLevel.NONE),
        (150, Profile.ADULT, MaskLevel.OPTIONAL),
        (150, Profile.ELDERLY, MaskLevel.RECOMMENDED),
        (300, Profile.ADULT, MaskLevel.RECOMMENDED),
    ],
)
def test_mask_levels(home, aqi, profile, level):
    from dataclasses import replace
    assert advise(plan(K.ERRAND), replace(home, profile=profile), aqi).mask.level is level


def test_children_get_a_kid_specific_fit_tip(home):
    tips = advise(plan(K.SCHOOL_RUN), home, 300).mask.fit_tips
    assert any("children" in t.lower() for t in tips)


def test_vulnerable_profiles_get_the_simple_recovery_list(home):
    from dataclasses import replace
    elderly = advise(plan(K.ERRAND), replace(home, profile=Profile.ELDERLY), 300)
    adult = advise(plan(K.ERRAND), replace(home, profile=Profile.ADULT), 300)
    assert len(elderly.recovery_tips) < len(adult.recovery_tips)


def test_travel_only_computed_for_trips(home):
    assert advise(plan(K.EXERCISE, km=0), home, 300).travel is None
    assert advise(plan(K.WORK_COMMUTE), home, 300).travel is not None


def test_disclaimer_is_always_present(home):
    assert "not medical advice" in advise(plan(K.ERRAND), home, 100).disclaimer


# ---- child rules apply only when children are actually travelling
def test_children_rules_apply_only_to_school_runs(home):
    from app.models import TravelMode

    def modes(advice):
        return {o.mode for o in advice.travel.options}

    errand = advise(plan(K.ERRAND, km=1.5), home, 350)  # family household, adult traveller
    school = advise(plan(K.SCHOOL_RUN, km=1.5), home, 350)
    assert TravelMode.WALK in modes(errand)
    assert TravelMode.WALK not in modes(school)
    assert not any("children" in tip.lower() for tip in errand.mask.fit_tips)
    assert any("children" in tip.lower() for tip in school.mask.fit_tips)


def test_traveller_profile_rules():
    from app.models import traveller_profile
    assert traveller_profile(plan(K.WORK_COMMUTE), Profile.FAMILY_WITH_CHILDREN) is Profile.ADULT
    assert traveller_profile(plan(K.SCHOOL_RUN), Profile.FAMILY_WITH_CHILDREN) is Profile.FAMILY_WITH_CHILDREN
    assert traveller_profile(plan(K.WORK_COMMUTE), Profile.ELDERLY) is Profile.ELDERLY


# ---- extra-care tips only when the air calls for them
def test_clean_air_gets_no_extra_care_tips(home):
    advice = advise(plan(K.WORK_COMMUTE), home, 60)
    assert advice.duration_tips == () and advice.before_after_tips == () and advice.recovery_tips == ()
    assert advice.travel is not None and advice.mask.level is MaskLevel.NONE


def test_polluted_air_gets_all_tip_groups(home):
    advice = advise(plan(K.WORK_COMMUTE), home, 180)
    assert advice.duration_tips and advice.before_after_tips and advice.recovery_tips

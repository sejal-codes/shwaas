import pytest

from app.models import HomeProfile, Plan, TravelMode


def valid_home():
    return {"profile": "adult", "windows": "closed", "cooking": "electric"}


def test_home_from_valid_dict():
    home = HomeProfile.from_dict(valid_home())
    assert home.heating.value == "none" and home.has_purifier is False


@pytest.mark.parametrize(
    "patch",
    [
        {"profile": "robot"},
        {"windows": 1},
        {"has_purifier": "yes"},
        {"indoor_smoking": 1},
    ],
)
def test_home_rejects_bad_values(patch):
    with pytest.raises(ValueError):
        HomeProfile.from_dict({**valid_home(), **patch})


def test_home_requires_core_fields():
    with pytest.raises(ValueError):
        HomeProfile.from_dict({"profile": "adult"})


def test_plan_from_valid_dict():
    plan = Plan.from_dict({"kind": "school_run", "timing": "fixed", "distance_km": 3,
                           "available_modes": ["walk", "metro_bus"]})
    assert plan.essential and plan.involves_travel
    assert plan.available_modes == {TravelMode.WALK, TravelMode.METRO_BUS}


@pytest.mark.parametrize(
    "data",
    [
        {"kind": "school_run", "timing": "fixed", "distance_km": -1},
        {"kind": "school_run", "timing": "fixed", "distance_km": 9999},
        {"kind": "school_run", "timing": "fixed", "distance_km": "3"},
        {"kind": "school_run", "timing": "fixed", "distance_km": True},
        {"kind": "school_run", "timing": "later"},
        {"kind": "school_run", "timing": "fixed", "available_modes": "walk"},
        {"kind": "school_run", "timing": "fixed", "available_modes": ["jetpack"]},
        {"kind": "school_run", "timing": "fixed", "distance_km": 2, "available_modes": []},
    ],
)
def test_plan_rejects_bad_values(data):
    with pytest.raises(ValueError):
        Plan.from_dict(data)

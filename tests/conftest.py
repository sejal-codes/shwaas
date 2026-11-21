import pytest

from app.models import CookingFuel, Heating, HomeProfile, Profile, WindowHabit


@pytest.fixture
def home() -> HomeProfile:
    """A typical family home: windows open, gas stove, no purifier."""
    return HomeProfile(
        profile=Profile.FAMILY_WITH_CHILDREN,
        windows=WindowHabit.OPEN,
        cooking=CookingFuel.GAS,
        heating=Heating.NONE,
    )

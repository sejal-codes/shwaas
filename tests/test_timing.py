from app.timing import suggest_better_time

HOURLY = {7: 410, 9: 380, 11: 290, 14: 300, 17: 340, 23: 100}


def test_suggests_cleanest_daytime_hour():
    s = suggest_better_time(HOURLY, current_hour=7)
    assert s.hour == 11 and s.forecast_aqi == 290
    assert s.improvement_pct == 29


def test_ignores_night_hours():
    s = suggest_better_time(HOURLY, current_hour=7)
    assert s.hour != 23


def test_none_when_gain_is_small():
    assert suggest_better_time({10: 300, 12: 290}, current_hour=10) is None


def test_none_without_current_reading_or_later_hours():
    assert suggest_better_time(HOURLY, current_hour=8) is None
    assert suggest_better_time(HOURLY, current_hour=17) is None

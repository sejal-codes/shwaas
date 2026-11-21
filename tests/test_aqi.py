import pytest

from app.aqi import Severity, normalize_aqi, pm25_to_naqi, severity, severity_alert


@pytest.mark.parametrize(
    "pm25, expected",
    [(0, 0), (30, 50), (60, 100), (90, 200), (120, 300), (250, 400), (380, 500), (900, 500)],
)
def test_pm25_band_edges(pm25, expected):
    assert pm25_to_naqi(pm25) == expected


def test_pm25_is_monotonic():
    values = [pm25_to_naqi(x) for x in range(0, 400, 5)]
    assert values == sorted(values)


@pytest.mark.parametrize("bad", [-1, float("nan"), "50", None, True])
def test_bad_readings_are_rejected(bad):
    with pytest.raises(ValueError):
        normalize_aqi(bad)
    with pytest.raises(ValueError):
        pm25_to_naqi(bad)


def test_normalize_caps_at_scale_top():
    assert normalize_aqi(700) == 500


@pytest.mark.parametrize(
    "aqi, expected",
    [
        (0, Severity.GOOD),
        (50, Severity.GOOD),
        (51, Severity.SATISFACTORY),
        (150, Severity.MODERATE),
        (250, Severity.POOR),
        (350, Severity.VERY_POOR),
        (401, Severity.SEVERE),
    ],
)
def test_severity_labels(aqi, expected):
    assert severity(aqi) is expected


def test_alert_only_when_dangerous():
    assert severity_alert(299) is None
    assert severity_alert(300) is not None

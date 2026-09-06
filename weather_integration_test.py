"""Focused tests for real weather evidence handling."""

from unittest.mock import patch

from weather_integration import fetch_weather_observation, rainfall_signal


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_real_weather_payload_is_normalized_with_provenance():
    payload = {
        "current": {
            "time": "2099-01-01T12:00",
            "rain": 30.0,
            "precipitation": 30.0,
        },
        "hourly": {"rain": [1.0] * 24},
    }
    with patch("requests.get", return_value=_Response(payload)):
        result = fetch_weather_observation(27.861, 86.476, max_age_hours=1000000)
    assert result["status"] == "SUCCESS"
    assert result["source"] == "Open-Meteo"
    assert result["rainfall_mmph"] == 30.0
    assert result["rainfall_24h_mm"] == 24.0
    assert result["signal"] == 0.6
    assert result["provenance"]["type"] == "REAL_WEATHER_DATA"


def test_weather_failure_is_unavailable_not_safe():
    with patch("requests.get", side_effect=RuntimeError("network down")):
        result = fetch_weather_observation(27.861, 86.476)
    assert result["status"] == "UNAVAILABLE"
    assert result["signal"] is None
    assert result["provenance"]["limitations"]


def test_rainfall_thresholds_are_bounded():
    assert rainfall_signal(0.0) == 0.0
    assert rainfall_signal(10.0) == 0.3
    assert rainfall_signal(25.0) == 0.6
    assert rainfall_signal(50.0) == 1.0


if __name__ == "__main__":
    test_real_weather_payload_is_normalized_with_provenance()
    test_weather_failure_is_unavailable_not_safe()
    test_rainfall_thresholds_are_bounded()
    print("Weather integration tests: PASS")

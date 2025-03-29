import pytest
from fire_risk_logic import calculate_fire_risk
import unittest.mock

def test_calculate_fire_risk_all_thresholds_exceeded():
    weather_data = {
        "air_temp": 28,  # Exceeds 25°C
        "relative_humidity": 10,  # Below 15%
        "wind_speed": 20,  # Exceeds 15 mph
        "wind_gust": 25,  # Exceeds 20 mph
        "soil_moisture_15cm": 5  # Below 10%
    }
    risk, explanation = calculate_fire_risk(weather_data)
    assert risk == "Red"
    assert "High fire risk" in explanation


def test_calculate_fire_risk_some_thresholds_exceeded():
    weather_data = {
        "air_temp": 28,  # Exceeds 25°C
        "relative_humidity": 10,  # Below 15%
        "wind_speed": 10,  # Within limits
        "wind_gust": 15,  # Within limits
        "soil_moisture_15cm": 5  # Below 10%
    }
    risk, explanation = calculate_fire_risk(weather_data)
    assert risk == "Orange"
    assert "Low or Moderate Fire Risk" in explanation


def test_calculate_fire_risk_no_thresholds_exceeded():
    weather_data = {
        "air_temp": 20,
        "relative_humidity": 20,
        "wind_speed": 5,
        "wind_gust": 10,
        "soil_moisture_15cm": 15
    }
    risk, explanation = calculate_fire_risk(weather_data)
    assert risk == "Orange"
    assert "Low or Moderate Fire Risk" in explanation


def test_calculate_fire_risk_missing_data():
    weather_data = {
        "air_temp": 28,
        "relative_humidity": 10,
        "wind_speed": 20
    }
    risk, explanation = calculate_fire_risk(weather_data)
    assert risk == "Orange"  # Should handle missing data gracefully
    assert "Low or Moderate Fire Risk" in explanation


def test_calculate_fire_risk_invalid_data():
    weather_data = {
        "air_temp": "high",  # Invalid data type
        "relative_humidity": 10,
        "wind_speed": 20,
        "wind_gust": 25,
        "soil_moisture_15cm": 5
    }
    risk, explanation = calculate_fire_risk(weather_data)
    assert risk == "Error"
    assert "Could not calculate risk" in explanation


def test_calculate_fire_risk_exception_handling():
    weather_data = {
        "air_temp": 28,
        "relative_humidity": 10,
        "wind_speed": 20,
        "wind_gust": 25,
        "soil_moisture_15cm": 5
    }

    # Mock a scenario where an exception might occur (e.g., during logging)
    with unittest.mock.patch('fire_risk_logic.logger.info') as mock_logger:
        mock_logger.side_effect = Exception("Mock logger error")
        risk, explanation = calculate_fire_risk(weather_data)
        assert risk == "Error"
        assert "Could not calculate risk" in explanation

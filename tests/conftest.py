import pytest
import os
import sys
import json
from datetime import datetime, timedelta
import pytz
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Add the parent directory to sys.path to import the main module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import main
from main import app, data_cache

@pytest.fixture
def client():
    """Return a TestClient for the FastAPI app."""
    return TestClient(app)

@pytest.fixture
def reset_cache():
    """Reset the data cache before and after each test."""
    # Store original cache state
    original_cache = {
        "synoptic_data": data_cache.synoptic_data,
        "wunderground_data": data_cache.wunderground_data,
        "fire_risk_data": data_cache.fire_risk_data,
        "last_updated": data_cache.last_updated,
        "last_valid_data": data_cache.last_valid_data.copy(),
        "cached_fields": data_cache.cached_fields.copy(),
        "using_cached_data": data_cache.using_cached_data
    }
    
    # Reset cache for test
    data_cache.synoptic_data = None
    data_cache.wunderground_data = None
    data_cache.fire_risk_data = None
    data_cache.last_updated = None
    data_cache.using_cached_data = False
    for field in data_cache.cached_fields:
        data_cache.cached_fields[field] = False
    
    yield
    
    # Restore original cache state
    data_cache.synoptic_data = original_cache["synoptic_data"]
    data_cache.wunderground_data = original_cache["wunderground_data"]
    data_cache.fire_risk_data = original_cache["fire_risk_data"]
    data_cache.last_updated = original_cache["last_updated"]
    data_cache.last_valid_data = original_cache["last_valid_data"]
    data_cache.cached_fields = original_cache["cached_fields"]
    data_cache.using_cached_data = original_cache["using_cached_data"]

@pytest.fixture
def mock_synoptic_response():
    """Return a mock Synoptic API response."""
    return {
        "STATION": [
            {
                "STID": "SEYC1",
                "OBSERVATIONS": {
                    "air_temp_value_1": {"value": 0.5},
                    "relative_humidity_value_1": {"value": 98.0},
                    "wind_speed_value_1": {"value": 0.0}
                }
            },
            {
                "STID": "C3DLA",
                "OBSERVATIONS": {
                    "soil_moisture_value_1": {"value": 22.0}
                }
            }
        ]
    }

@pytest.fixture
def mock_wunderground_response():
    """Return a mock Weather Underground API response."""
    return {
        "observations": [
            {
                "imperial": {
                    "windGust": 3.0
                }
            }
        ]
    }

@pytest.fixture
def mock_api_responses(mock_synoptic_response, mock_wunderground_response):
    """Mock both API responses."""
    with patch('main.get_weather_data', return_value=mock_synoptic_response), \
         patch('main.get_wunderground_data', return_value=mock_wunderground_response):
        yield

@pytest.fixture
def mock_failed_synoptic_api():
    """Mock a failed Synoptic API response."""
    with patch('main.get_weather_data', return_value=None):
        yield

@pytest.fixture
def mock_failed_wunderground_api():
    """Mock a failed Weather Underground API response."""
    with patch('main.get_wunderground_data', return_value=None):
        yield

@pytest.fixture
def mock_partial_api_failure(mock_synoptic_response):
    """Mock a partial API failure where some fields are missing."""
    # Create a copy of the mock response with some fields set to None
    partial_response = mock_synoptic_response.copy()
    partial_response["STATION"][0]["OBSERVATIONS"]["air_temp_value_1"]["value"] = None
    partial_response["STATION"][1]["OBSERVATIONS"]["soil_moisture_value_1"]["value"] = None
    
    with patch('main.get_weather_data', return_value=partial_response), \
         patch('main.get_wunderground_data', return_value=None):
        yield

@pytest.fixture
def populate_cache_with_valid_data(mock_synoptic_response, mock_wunderground_response):
    """Populate the cache with valid data."""
    # Create a fire risk data object
    weather_data = {
        "air_temp": 0.5,
        "relative_humidity": 98.0,
        "wind_speed": 0.0,
        "soil_moisture_15cm": 22.0,
        "wind_gust": 3.0,
        "data_sources": {
            "weather_station": "SEYC1",
            "soil_moisture_station": "C3DLA",
            "wind_gust_station": "KCASIERR68"
        },
        "cached_fields": {
            "temperature": False,
            "humidity": False,
            "wind_speed": False,
            "soil_moisture": False,
            "wind_gust": False
        }
    }
    
    risk, explanation = main.calculate_fire_risk(weather_data)
    fire_risk_data = {"risk": risk, "explanation": explanation, "weather": weather_data}
    
    # Update the cache
    pacific_tz = pytz.timezone('America/Los_Angeles')
    current_time = datetime.now(pacific_tz)
    
    data_cache.update_cache(mock_synoptic_response, mock_wunderground_response, fire_risk_data)
    
    return fire_risk_data

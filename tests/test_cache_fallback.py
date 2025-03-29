import pytest
import asyncio
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from cache import DataCache
from config import TIMEZONE


@pytest.fixture
def sample_data_cache():
    """Create a test instance of DataCache with default values."""
    return DataCache()


def test_cache_init_default_values(sample_data_cache):
    """Test that cache is initialized with default values for all fields."""
    # Check that default values are set
    assert sample_data_cache.last_valid_data["fields"]["temperature"]["value"] is not None
    assert sample_data_cache.last_valid_data["fields"]["humidity"]["value"] is not None
    assert sample_data_cache.last_valid_data["fields"]["wind_speed"]["value"] is not None
    assert sample_data_cache.last_valid_data["fields"]["soil_moisture"]["value"] is not None
    assert sample_data_cache.last_valid_data["fields"]["wind_gust"]["value"] is not None
    
    # Check that timestamps are set
    assert sample_data_cache.last_valid_data["fields"]["temperature"]["timestamp"] is not None
    assert sample_data_cache.last_valid_data["timestamp"] is not None
    
    # Check that we start with all fields marked as using cached values
    assert all(sample_data_cache.cached_fields.values())
    assert sample_data_cache.using_cached_data is True


def test_get_field_value_direct(sample_data_cache):
    """Test that get_field_value returns direct values from fire_risk_data if available."""
    # Setup mock fire_risk_data with direct values
    sample_data_cache.fire_risk_data = {
        "weather": {
            "air_temp": 20.0,
            "relative_humidity": 60.0,
            "wind_speed": 10.0,
            "soil_moisture_15cm": 30.0,
            "wind_gust": 15.0
        }
    }
    
    # Test each field
    assert sample_data_cache.get_field_value("temperature") == 20.0
    assert sample_data_cache.get_field_value("humidity") == 60.0
    assert sample_data_cache.get_field_value("wind_speed") == 10.0
    assert sample_data_cache.get_field_value("soil_moisture") == 30.0
    assert sample_data_cache.get_field_value("wind_gust") == 15.0
    
    # Verify no cached flags are set since we're using direct values
    assert not any(sample_data_cache.cached_fields.values())
    assert not sample_data_cache.using_cached_data


def test_get_field_value_cached(sample_data_cache):
    """Test that get_field_value returns cached values when direct values are not available."""
    # Setup empty fire_risk_data
    sample_data_cache.fire_risk_data = {"weather": {}}
    
    # Setup custom cached values
    current_time = datetime.now(TIMEZONE)
    sample_data_cache.last_valid_data["fields"]["temperature"]["value"] = 25.0
    sample_data_cache.last_valid_data["fields"]["temperature"]["timestamp"] = current_time
    
    # Get value - should use cached value
    assert sample_data_cache.get_field_value("temperature") == 25.0
    
    # Verify cache flags are set
    assert sample_data_cache.cached_fields["temperature"] is True
    assert sample_data_cache.using_cached_data is True


def test_get_field_value_default(sample_data_cache):
    """Test that get_field_value returns default values when neither direct nor cached values are available."""
    # Setup empty fire_risk_data
    sample_data_cache.fire_risk_data = {"weather": {}}
    
    # Clear cached values
    sample_data_cache.last_valid_data["fields"]["temperature"]["value"] = None
    
    # Get value - should use default value
    assert sample_data_cache.get_field_value("temperature") == sample_data_cache.DEFAULT_VALUES["temperature"]
    
    # Verify cache flags are set
    assert sample_data_cache.cached_fields["temperature"] is True
    assert sample_data_cache.using_cached_data is True


def test_ensure_complete_weather_data(sample_data_cache):
    """Test that ensure_complete_weather_data fills in missing fields with cached or default values."""
    # Setup incomplete weather data
    incomplete_weather = {
        "air_temp": 20.0,
        "relative_humidity": None,  # Missing value
        # Missing wind_speed entirely
        "soil_moisture_15cm": 30.0,
        "wind_gust": None  # Missing value
    }
    
    # Setup some cached values
    current_time = datetime.now(TIMEZONE)
    sample_data_cache.last_valid_data["fields"]["humidity"]["value"] = 55.0
    sample_data_cache.last_valid_data["fields"]["humidity"]["timestamp"] = current_time
    
    # Complete the weather data
    completed_weather = sample_data_cache.ensure_complete_weather_data(incomplete_weather)
    
    # Check that all fields are now present and have values
    assert completed_weather["air_temp"] == 20.0  # Original value preserved
    assert completed_weather["relative_humidity"] == 55.0  # Used cached value
    assert completed_weather["wind_speed"] == sample_data_cache.DEFAULT_VALUES["wind_speed"]  # Used default
    assert completed_weather["soil_moisture_15cm"] == 30.0  # Original value preserved
    assert completed_weather["wind_gust"] == sample_data_cache.DEFAULT_VALUES["wind_gust"]  # Used default
    
    # Verify that the cache flags were set for the fields that used cached/default values
    assert sample_data_cache.cached_fields["humidity"] is True
    assert sample_data_cache.cached_fields["wind_speed"] is True
    assert sample_data_cache.cached_fields["wind_gust"] is True
    assert sample_data_cache.using_cached_data is True


def test_complete_weather_data_never_returns_none(sample_data_cache):
    """Test that ensure_complete_weather_data never returns None for any weather metric."""
    # Setup completely empty weather data
    empty_weather = {}
    
    # Complete the weather data
    completed_weather = sample_data_cache.ensure_complete_weather_data(empty_weather)
    
    # Verify that no values are None
    assert completed_weather["air_temp"] is not None
    assert completed_weather["relative_humidity"] is not None
    assert completed_weather["wind_speed"] is not None
    assert completed_weather["soil_moisture_15cm"] is not None
    assert completed_weather["wind_gust"] is not None
    
    # Verify all cache flags are set
    assert all(sample_data_cache.cached_fields.values())
    assert sample_data_cache.using_cached_data is True

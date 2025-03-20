import pytest
import json
from datetime import datetime, timedelta
import pytz
from unittest.mock import patch, MagicMock

from main import data_cache, refresh_data_cache

@pytest.mark.asyncio
async def test_cache_initialization():
    """Test that the cache is properly initialized."""
    assert data_cache is not None
    assert data_cache.synoptic_data is None or isinstance(data_cache.synoptic_data, dict)
    assert data_cache.wunderground_data is None or isinstance(data_cache.wunderground_data, dict)
    assert data_cache.fire_risk_data is None or isinstance(data_cache.fire_risk_data, dict)
    assert isinstance(data_cache.cached_fields, dict)
    assert len(data_cache.cached_fields) == 5  # temperature, humidity, wind_speed, soil_moisture, wind_gust

@pytest.mark.asyncio
async def test_cache_update(reset_cache, mock_synoptic_response, mock_wunderground_response):
    """Test that the cache is properly updated with new data."""
    # Create a fire risk data object
    weather_data = {
        "air_temp": 0.5,
        "relative_humidity": 98.0,
        "wind_speed": 0.0,
        "soil_moisture_15cm": 22.0,
        "wind_gust": 3.0
    }
    
    fire_risk_data = {"risk": "Orange", "explanation": "Test explanation", "weather": weather_data}
    
    # Update the cache
    data_cache.update_cache(mock_synoptic_response, mock_wunderground_response, fire_risk_data)
    
    # Check that the cache was updated
    assert data_cache.synoptic_data == mock_synoptic_response
    assert data_cache.wunderground_data == mock_wunderground_response
    assert data_cache.fire_risk_data == fire_risk_data
    assert data_cache.last_updated is not None
    
    # Check that the last_valid_data was updated
    assert data_cache.last_valid_data["synoptic_data"] == mock_synoptic_response
    assert data_cache.last_valid_data["wunderground_data"] == mock_wunderground_response
    assert data_cache.last_valid_data["fire_risk_data"] == fire_risk_data
    assert data_cache.last_valid_data["timestamp"] is not None
    
    # Check that individual fields were updated
    assert data_cache.last_valid_data["fields"]["temperature"]["value"] == 0.5
    assert data_cache.last_valid_data["fields"]["humidity"]["value"] == 98.0
    assert data_cache.last_valid_data["fields"]["wind_speed"]["value"] == 0.0
    assert data_cache.last_valid_data["fields"]["soil_moisture"]["value"] == 22.0
    assert data_cache.last_valid_data["fields"]["wind_gust"]["value"] == 3.0

@pytest.mark.asyncio
async def test_complete_api_failure_with_cache(reset_cache, mock_failed_synoptic_api, mock_failed_wunderground_api, populate_cache_with_valid_data):
    """Test that the system uses cached data when both APIs fail."""
    # First, populate the cache with valid data
    original_data = populate_cache_with_valid_data
    
    # Now simulate a complete API failure
    background_tasks = MagicMock()
    success = await refresh_data_cache(background_tasks, force=True)
    
    # Check that the refresh was successful (using cached data)
    assert success is True
    
    # Check that we're using cached data
    assert data_cache.using_cached_data is True
    
    # Check that the fire_risk_data has a cached_data field
    assert "cached_data" in data_cache.fire_risk_data
    assert data_cache.fire_risk_data["cached_data"]["is_cached"] is True

@pytest.mark.asyncio
async def test_partial_api_failure(reset_cache, mock_partial_api_failure, populate_cache_with_valid_data):
    """Test that the system uses cached data for missing fields when some API calls partially fail."""
    # First, populate the cache with valid data
    original_data = populate_cache_with_valid_data
    
    # Now simulate a partial API failure
    background_tasks = MagicMock()
    success = await refresh_data_cache(background_tasks, force=True)
    
    # Check that the refresh was successful
    assert success is True
    
    # Check that we're using cached data for some fields
    assert data_cache.using_cached_data is True
    
    # Check that the specific fields are marked as using cached data
    assert data_cache.cached_fields["temperature"] is True
    assert data_cache.cached_fields["soil_moisture"] is True
    
    # Other fields should not be using cached data
    assert data_cache.cached_fields["humidity"] is False
    assert data_cache.cached_fields["wind_speed"] is False

@pytest.mark.asyncio
async def test_cache_expiration(reset_cache, populate_cache_with_valid_data):
    """Test that the cache correctly identifies when data is stale."""
    # First, populate the cache with valid data
    original_data = populate_cache_with_valid_data
    
    # Check that the data is fresh
    assert data_cache.is_stale() is False
    
    # Manually set the last_updated time to be older
    pacific_tz = pytz.timezone('America/Los_Angeles')
    data_cache.last_updated = datetime.now(pacific_tz) - timedelta(minutes=20)
    
    # Check that the data is now stale
    assert data_cache.is_stale() is True
    
    # Check if it's critically stale (should not be yet)
    assert data_cache.is_critically_stale() is False
    
    # Make it critically stale
    data_cache.last_updated = datetime.now(pacific_tz) - timedelta(minutes=40)
    
    # Check that it's now critically stale
    assert data_cache.is_critically_stale() is True

@pytest.mark.asyncio
async def test_cached_fields_in_response(reset_cache, mock_partial_api_failure, populate_cache_with_valid_data, client):
    """Test that the API response includes information about which fields are using cached data."""
    # First, populate the cache with valid data
    original_data = populate_cache_with_valid_data
    
    # Now simulate a partial API failure
    background_tasks = MagicMock()
    await refresh_data_cache(background_tasks, force=True)
    
    # Make a request to the API
    response = client.get("/fire-risk")
    
    # Check that the response is successful
    assert response.status_code == 200
    
    # Parse the response
    data = response.json()
    
    # Check that the response includes cache information
    assert "cache_info" in data
    assert data["cache_info"]["using_cached_data"] is True
    
    # Check that the weather data includes cached_fields information
    assert "weather" in data
    assert "cached_fields" in data["weather"]
    
    # Check that the specific fields are marked as using cached data
    assert data["weather"]["cached_fields"]["temperature"] is True
    assert data["weather"]["cached_fields"]["soil_moisture"] is True

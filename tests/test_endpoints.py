import pytest
from unittest.mock import patch, MagicMock

from main import app, data_cache, refresh_data_cache

@pytest.mark.asyncio
async def test_fire_risk_endpoint(client, reset_cache, mock_api_responses):
    """Test that the /fire-risk endpoint returns the correct data."""
    # Make a request to the API
    response = client.get("/fire-risk")
    
    # Check that the response is successful
    assert response.status_code == 200
    
    # Parse the response
    data = response.json()
    
    # Check that the response includes the expected fields
    assert "risk" in data
    assert "explanation" in data
    assert "weather" in data
    assert "cache_info" in data
    
    # Check that the weather data includes the expected fields
    assert "air_temp" in data["weather"]
    assert "relative_humidity" in data["weather"]
    assert "wind_speed" in data["weather"]
    assert "soil_moisture_15cm" in data["weather"]
    assert "wind_gust" in data["weather"]
    
    # Check that the cache info includes the expected fields
    assert "last_updated" in data["cache_info"]
    assert "is_fresh" in data["cache_info"]
    assert "refresh_in_progress" in data["cache_info"]
    assert "using_cached_data" in data["cache_info"]

@pytest.mark.asyncio
async def test_fire_risk_endpoint_with_wait_for_fresh(client, reset_cache, mock_api_responses):
    """Test that the /fire-risk endpoint with wait_for_fresh=true waits for fresh data."""
    # Make a request to the API with wait_for_fresh=true
    response = client.get("/fire-risk?wait_for_fresh=true")
    
    # Check that the response is successful
    assert response.status_code == 200
    
    # Parse the response
    data = response.json()
    
    # Check that the response includes the expected fields
    assert "risk" in data
    assert "explanation" in data
    assert "weather" in data
    assert "cache_info" in data
    
    # Check that the data is fresh
    assert data["cache_info"]["is_fresh"] is True

@pytest.mark.asyncio
async def test_force_cached_mode_endpoint(client, reset_cache, populate_cache_with_valid_data):
    """Test that the /force-cached-mode endpoint forces the system to use cached data."""
    # First, populate the cache with valid data
    original_data = populate_cache_with_valid_data
    
    # Make a request to the force-cached-mode endpoint
    response = client.get("/force-cached-mode", follow_redirects=False)
    
    # Check that the response is a redirect
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    
    # Check that the system is now using cached data
    assert data_cache.using_cached_data is True
    
    # Check that the fire_risk_data has a cached_data field
    assert "cached_data" in data_cache.fire_risk_data
    assert data_cache.fire_risk_data["cached_data"]["is_cached"] is True

@pytest.mark.asyncio
async def test_reset_cached_mode_endpoint(client, reset_cache, populate_cache_with_valid_data):
    """Test that the /reset-cached-mode endpoint resets the system to normal operation."""
    # First, populate the cache with valid data
    original_data = populate_cache_with_valid_data
    
    # Force the system to use cached data
    data_cache.using_cached_data = True
    data_cache.fire_risk_data["cached_data"] = {
        "is_cached": True,
        "original_timestamp": data_cache.last_updated.isoformat(),
        "age": "0 minutes"
    }
    
    # Make a request to the reset-cached-mode endpoint
    with patch('main.refresh_data_cache', return_value=True):
        response = client.get("/reset-cached-mode")
    
    # Check that the response is successful
    assert response.status_code == 200
    
    # Check that the system is no longer using cached data
    assert data_cache.using_cached_data is False
    
    # Check that the cached_data field has been removed from fire_risk_data
    assert "cached_data" not in data_cache.fire_risk_data

@pytest.mark.asyncio
async def test_test_partial_failure_endpoint(client, reset_cache, populate_cache_with_valid_data):
    """Test that the /test-partial-failure endpoint simulates a partial API failure."""
    # First, populate the cache with valid data
    original_data = populate_cache_with_valid_data
    
    # Make a request to the test-partial-failure endpoint
    with patch('main.refresh_data_cache', return_value=True):
        response = client.get("/test-partial-failure")
    
    # Check that the response is successful
    assert response.status_code == 200
    
    # Check that the response includes the expected content
    assert "Partial API Failure Detected" in response.text
    assert "CACHED" in response.text
    assert "FRESH" in response.text
    
    # Check that the system is simulating a partial API failure
    assert data_cache.fire_risk_data["weather"]["air_temp"] is None
    assert data_cache.fire_risk_data["weather"]["soil_moisture_15cm"] is None

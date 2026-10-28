"""Integration tests for fire risk dashboard endpoints."""

import pytest
# Removed TestClient import
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from fastapi import BackgroundTasks
from datetime import datetime, timedelta

# Removed app import, assuming it's available via client fixture context
from cache import data_cache
from config import TIMEZONE

# Removed local client = TestClient(app)


import asyncio
from asyncio.events import AbstractEventLoopPolicy
from asyncio import get_event_loop_policy

# Sample data to simulate cache content after a successful refresh
SAMPLE_FIRE_RISK_DATA = {
    "risk": "Low",
    "explanation": "Conditions are not conducive to fire.",
    "weather": {
        "air_temp": 20.0,
        "relative_humidity": 70.0,
        "wind_speed": 5.0,
        "soil_moisture_15cm": 40.0,
        "wind_gust": 8.0,
        "data_sources": {},
        "wind_gust_stations": {},
        "data_status": {"issues": []},
        "cache_timestamp": datetime.now(TIMEZONE).isoformat(),
        "cached_fields": {}
    },
    "thresholds": {},
    "modal_content": {}
}

# Removed session-scoped event_loop_policy fixture to let pytest-asyncio manage the loop


@pytest.fixture(autouse=True)
async def reset_cache():
    """Reset the cache before each test."""
    # Reset cache state manually
    data_cache.synoptic_data = None
    data_cache.wunderground_data = None
    data_cache.fire_risk_data = None
    data_cache.last_updated = None
    data_cache.update_in_progress = False
    data_cache.last_update_success = False
    data_cache.last_valid_data = {
        "fields": {
            "temperature": {"value": None, "timestamp": None},
            "humidity": {"value": None, "timestamp": None},
            "wind_speed": {"value": None, "timestamp": None},
            "soil_moisture": {"value": None, "timestamp": None},
            "wind_gust": {"value": None, "timestamp": None, "stations": {}},
        },
        "synoptic_data": None,
        "wunderground_data": None,
        "fire_risk_data": None,
        "timestamp": None,
    }
    data_cache.cached_fields = {k: False for k in data_cache.cached_fields}
    data_cache.using_cached_data = False
    # Ensure the event is clear
    data_cache._update_complete_event.clear()


# --- Endpoint Tests (Mocking refresh_data_cache) ---

@pytest.mark.asyncio
@patch('endpoints.refresh_data_cache', new_callable=AsyncMock)
async def test_initial_cache_empty(mock_refresh, client): # Added client fixture
    """Test the /fire-risk endpoint when the cache is initially empty."""
    # Configure mock to simulate a successful refresh
    async def side_effect(*args, **kwargs):
        data_cache.fire_risk_data = SAMPLE_FIRE_RISK_DATA.copy()
        data_cache.last_updated = datetime.now(TIMEZONE)
        data_cache.last_update_success = True
        data_cache._update_complete_event.set() # Simulate event set by refresh
        return True
    mock_refresh.side_effect = side_effect

    response = await client.get("/fire-risk") # Use await and fixture client

    assert response.status_code == 200
    mock_refresh.assert_called_once() # Ensure refresh was called because cache was empty
    data = response.json()
    assert data["cache_info"]["last_updated"] is not None # Should be updated now
    assert data["cache_info"]["is_fresh"] is True
    assert data["cache_info"]["refresh_in_progress"] is False
    assert data["cache_info"]["using_cached_data"] is False
    assert data["risk"] == SAMPLE_FIRE_RISK_DATA["risk"]


@pytest.mark.asyncio
@patch('endpoints.refresh_data_cache', new_callable=AsyncMock)
async def test_cache_stale_refresh_background(mock_refresh, client): # Added client fixture
    """Test /fire-risk triggers background refresh when cache is stale."""
    # Setup: Populate cache and make it stale
    data_cache.fire_risk_data = SAMPLE_FIRE_RISK_DATA.copy()
    data_cache.last_updated = datetime.now(TIMEZONE) - timedelta(minutes=90) # Stale
    data_cache.last_update_success = True

    # Configure mock refresh (won't be awaited by endpoint in this case)
    mock_refresh.return_value = True

    response = await client.get("/fire-risk") # Use await and fixture client

    assert response.status_code == 200
    # Refresh should be called in the background
    mock_refresh.assert_called_once()
    data = response.json()
    # Should return stale data immediately
    assert data["cache_info"]["is_fresh"] is False
    assert data["risk"] == SAMPLE_FIRE_RISK_DATA["risk"] # Returns the stale data


@pytest.mark.asyncio
@patch('endpoints.refresh_data_cache', new_callable=AsyncMock)
async def test_wait_for_fresh(mock_refresh, client): # Added client fixture
    """Test the wait_for_fresh=true parameter."""
    # Setup: Populate cache and make it stale
    data_cache.fire_risk_data = SAMPLE_FIRE_RISK_DATA.copy()
    stale_time = datetime.now(TIMEZONE) - timedelta(minutes=90)
    data_cache.last_updated = stale_time
    data_cache.last_update_success = True

    # Configure mock to simulate a successful refresh completing
    fresh_data = SAMPLE_FIRE_RISK_DATA.copy()
    fresh_data["explanation"] = "Fresh data explanation"
    fresh_time = datetime.now(TIMEZONE)
    async def side_effect(*args, **kwargs):
        # Simulate refresh updating the cache
        data_cache.fire_risk_data = fresh_data
        data_cache.last_updated = fresh_time
        data_cache.last_update_success = True
        data_cache._update_complete_event.set() # Refresh sets the event
        return True
    mock_refresh.side_effect = side_effect

    # Request fresh data - this should now wait for the mocked refresh
    response = await client.get("/fire-risk?wait_for_fresh=true") # Use await and fixture client

    assert response.status_code == 200
    mock_refresh.assert_called_once() # Refresh was called
    data = response.json()
    assert data["cache_info"]["is_fresh"] is True
    assert data["explanation"] == "Fresh data explanation" # Check it's the fresh data
    assert datetime.fromisoformat(data["cache_info"]["last_updated"]) > stale_time


@pytest.mark.asyncio
@patch('endpoints.refresh_data_cache', new_callable=AsyncMock)
async def test_test_mode_toggle(mock_refresh, admin_client):
    client = admin_client
    """Test the test mode toggle endpoint and its effect."""
    # Setup: the dashboard is showing current data, and earlier valid data exists for caching fallback
    data_cache.fire_risk_data = SAMPLE_FIRE_RISK_DATA.copy()
    data_cache.last_updated = datetime.now(TIMEZONE)
    data_cache.last_valid_data["fire_risk_data"] = SAMPLE_FIRE_RISK_DATA.copy()
    data_cache.last_valid_data["timestamp"] = datetime.now(TIMEZONE) - timedelta(hours=1)

    # Enable test mode
    response_enable = await client.post("/toggle-test-mode?enable=true") # Use await and fixture client
    assert response_enable.status_code == 200
    assert response_enable.json()["mode"] == "test"
    assert data_cache.using_cached_data is True

    # Check /fire-risk returns cached data (refresh shouldn't be called by endpoint)
    response_fire_risk_cached = await client.get("/fire-risk") # Use await and fixture client
    assert response_fire_risk_cached.status_code == 200
    assert "cached_data" in response_fire_risk_cached.json()
    mock_refresh.assert_not_called() # Refresh shouldn't be called when forced cache is used

    # Disable test mode (this call *will* trigger a refresh)
    async def side_effect_disable(*args, **kwargs):
        data_cache.fire_risk_data = SAMPLE_FIRE_RISK_DATA.copy() # Simulate refresh
        data_cache.last_updated = datetime.now(TIMEZONE)
        data_cache.last_update_success = True
        data_cache.using_cached_data = False # Refresh disables this
        data_cache._update_complete_event.set()
        return True
    mock_refresh.side_effect = side_effect_disable

    response_disable = await client.post("/toggle-test-mode?enable=false") # Use await and fixture client
    assert response_disable.status_code == 200
    assert response_disable.json()["mode"] == "normal"
    assert data_cache.using_cached_data is False
    mock_refresh.assert_called_once() # Refresh called by disable toggle

    # Check /fire-risk returns fresh data
    response_fire_risk_fresh = await client.get("/fire-risk") # Use await and fixture client
    assert response_fire_risk_fresh.status_code == 200
    assert "cached_data" not in response_fire_risk_fresh.json()


# --- refresh_data_cache Integration Tests (Mocking API Clients) ---

def synoptic_response(air_temp, humidity, wind_speed, wind_gust, soil_moisture):
    """A Synoptic API response from the three stations the dashboard reads."""
    return {
        "STATION": [
            {"STID": "SEYC1", "OBSERVATIONS": {
                "air_temp_value_1": {"value": air_temp},
                "relative_humidity_value_1": {"value": humidity}}},
            {"STID": "C3DLA", "OBSERVATIONS": {
                "soil_moisture_value_1": {"value": soil_moisture}}},
            {"STID": "629PG", "OBSERVATIONS": {
                "wind_speed_value_1": {"value": wind_speed},
                "wind_gust_value_1": {"value": wind_gust}}}
        ]
    }


async def refresh_with_response(response):
    """Run a real refresh where only the Synoptic API call (and email) is faked."""
    from cache_refresh import refresh_data_cache
    with patch('cache_refresh.get_synoptic_data', return_value=response) as mock_synoptic, \
         patch('cache_refresh.send_orange_to_red_alert') as mock_send_alert:
        success = await refresh_data_cache(background_tasks=Mock(spec=BackgroundTasks), force=True)
    mock_synoptic.assert_called_once()
    mock_send_alert.assert_not_called()  # No previous Orange level, so never an alert
    return success


@pytest.mark.asyncio
async def test_api_client_integration(real_cache):
    """A response with no observations still refreshes, filling every value from the cache defaults."""
    response = {"STATION": [{"STID": "SEYC1", "OBSERVATIONS": {}}]}

    assert await refresh_with_response(response) is True

    weather = real_cache.fire_risk_data["weather"]
    assert weather["air_temp"] == real_cache.DEFAULT_VALUES["temperature"]
    assert weather["soil_moisture_15cm"] == real_cache.DEFAULT_VALUES["soil_moisture"]
    assert "Temperature data missing from station SEYC1" in weather["data_status"]["issues"]
    assert real_cache.last_update_success is True
    assert real_cache.using_cached_data is True


@pytest.mark.asyncio
@pytest.mark.parametrize("readings, expected_risk", [
    ((25.5, 60.2, 15.3, 20.1, 35.7), "Orange"),  # Hot and windy, but humid with moist soil
    ((30.0, 10.0, 12.0, 20.0, 5.0), "Red"),      # Every threshold exceeded
])
async def test_data_processing_integration(real_cache, readings, expected_risk):
    """Station readings flow through processing and the risk rules into the dashboard data."""
    air_temp, humidity, wind_speed, wind_gust, soil_moisture = readings

    assert await refresh_with_response(synoptic_response(*readings)) is True

    weather = real_cache.fire_risk_data["weather"]
    assert weather["air_temp"] == air_temp
    assert weather["relative_humidity"] == humidity
    assert weather["wind_speed"] == wind_speed
    assert weather["wind_gust"] == wind_gust
    assert weather["soil_moisture_15cm"] == soil_moisture
    assert weather["data_status"]["issues"] == []
    assert real_cache.fire_risk_data["risk"] == expected_risk
    assert real_cache.previous_risk_level == expected_risk
    assert real_cache.using_cached_data is False

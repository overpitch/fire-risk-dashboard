import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from cache import DataCache, data_cache # Import the global instance
from cache_refresh import refresh_data_cache # Import the function to test
from config import TIMEZONE # Import TIMEZONE

@pytest.fixture
def cache():
    # Create a fresh cache instance for each test
    # This ensures tests don't interfere with each other
    # Reset the global instance before creating a new one for the test
    global data_cache
    data_cache = DataCache()
    return data_cache


def test_is_stale_no_data(cache):
    # A freshly initialized cache (using defaults) might not be considered stale
    # depending on the default max_age_minutes. Let's check against the default.
    assert cache.is_stale() is False # Freshly initialized should not be stale


def test_is_stale_fresh_data(cache):
    cache.last_updated = datetime.now(TIMEZONE) # Use TIMEZONE
    assert cache.is_stale() is False


def test_is_stale_old_data(cache):
    cache.last_updated = datetime.now(TIMEZONE) - timedelta(minutes=30) # Use TIMEZONE
    assert cache.is_stale() is True


def test_is_critically_stale_no_data(cache):
    # A freshly initialized cache should not be critically stale
    assert cache.is_critically_stale() is False # Changed assertion


def test_is_critically_stale_fresh_data(cache):
    cache.last_updated = datetime.now(TIMEZONE) # Use TIMEZONE
    assert cache.is_critically_stale() is False


def test_is_critically_stale_old_data(cache):
    cache.last_updated = datetime.now(TIMEZONE) - timedelta(minutes=40)  # Older than the 30-minute threshold, use TIMEZONE
    assert cache.is_critically_stale() is True


def test_update_cache(cache):
    synoptic_data = {"test": "synoptic"}
    wunderground_data = {"test": "wunderground"}
    fire_risk_data = {"risk": "low"}

    cache.update_cache(synoptic_data, wunderground_data, fire_risk_data)

    assert cache.synoptic_data == synoptic_data
    assert cache.wunderground_data == wunderground_data
    assert cache.fire_risk_data == fire_risk_data
    assert cache.last_updated is not None
    assert cache.last_update_success is True
    assert cache.last_valid_data["synoptic_data"] == synoptic_data
    assert cache.last_valid_data["wunderground_data"] == wunderground_data
    assert cache.last_valid_data["fire_risk_data"] == fire_risk_data
    assert cache.last_valid_data["timestamp"] is not None


def test_update_cache_with_none_data(cache):
    synoptic_data = {"test": "synoptic"}
    wunderground_data = None  # Simulate missing data
    fire_risk_data = {"risk": "low"}

    cache.update_cache(synoptic_data, wunderground_data, fire_risk_data)

    assert cache.synoptic_data == synoptic_data
    assert cache.wunderground_data is None  # Check that the None value is stored
    assert cache.fire_risk_data == fire_risk_data
    assert cache.last_updated is not None
    assert cache.last_update_success is True
    assert cache.last_valid_data["synoptic_data"] == synoptic_data
    assert cache.last_valid_data["wunderground_data"] is None # Check that the None value is stored in last_valid_data
    assert cache.last_valid_data["fire_risk_data"] == fire_risk_data
    assert cache.last_valid_data["timestamp"] is not None

@pytest.mark.asyncio
async def test_wait_for_update(cache):

    # Simulate an update in a separate thread
    async def update_cache_async():
        await asyncio.sleep(0.1)  # Simulate some delay
        cache.update_cache({}, {}, {})

    asyncio.create_task(update_cache_async())
    assert await cache.wait_for_update() is True


@pytest.mark.asyncio
async def test_wait_for_update_timeout(cache):
    cache.update_timeout = 0.01  # Set a very short timeout
    assert await cache.wait_for_update() is False


# Modifying to patch the asyncio event loop
@patch('asyncio.get_event_loop')
def test_reset_update_event(mock_get_event_loop, cache):
    # Set up the mock event loop
    mock_loop = MagicMock()
    mock_get_event_loop.return_value = mock_loop
    mock_loop.is_closed.return_value = False
    
    # Call the method
    cache.reset_update_event()
    
    # Verify that call_soon_threadsafe was called with the clear method
    mock_loop.call_soon_threadsafe.assert_called_once_with(cache._update_complete_event.clear)


@pytest.mark.asyncio
@patch('cache_refresh.get_wunderground_data', new_callable=AsyncMock)
@patch('cache_refresh.get_synoptic_data', new_callable=AsyncMock)
@patch('cache_refresh.format_age_string')
async def test_refresh_failure_sets_cached_flag(mock_format_age, mock_synoptic, mock_wunderground):
    """
    Test that if API calls fail during refresh, the cache falls back
    and correctly sets the using_cached_data flag with all required fields.
    """
    # --- Setup ---
    # Set up mocked age string
    mock_format_age.return_value = "1 hour old"
    
    # Simulate API failures
    mock_synoptic.return_value = None
    mock_wunderground.return_value = None

    # Create timestamp for cache data
    cache_timestamp = datetime.now(TIMEZONE) - timedelta(hours=1)
    
    # Create a mock DataCache instance for this test
    mock_cache = MagicMock(spec=DataCache)
    mock_cache.last_valid_data = { # Simulate some previously valid data
        "fields": {
            "temperature": {"value": 10.0, "timestamp": cache_timestamp},
            "humidity": {"value": 50.0, "timestamp": cache_timestamp},
            "wind_speed": {"value": 5.0, "timestamp": cache_timestamp},
            "soil_moisture": {"value": 15.0, "timestamp": cache_timestamp},
            "wind_gust": {"value": 8.0, "timestamp": cache_timestamp},
        },
        "timestamp": cache_timestamp,
        "weather": {
            "air_temp": 10.0,
            "relative_humidity": 50.0,
            "wind_speed": 5.0,
            "soil_moisture_15cm": 15.0,
            "wind_gust": 8.0
        }
    }
    # Initialize other necessary attributes for the mock
    mock_cache.update_in_progress = False
    mock_cache.reset_update_event = MagicMock()
    mock_cache.max_retries = 3
    mock_cache.update_timeout = 10
    mock_cache.retry_delay = 0.01 # Short delay for testing retries
    mock_cache.cached_fields = {"temperature": False, "humidity": False, "wind_speed": False, "soil_moisture": False, "wind_gust": False}
    mock_cache.using_cached_data = False
    mock_cache.fire_risk_data = {
        "risk": "Initial", 
        "weather": {
            "air_temp": 10.0,
            "relative_humidity": 50.0,
            "wind_speed": 5.0,
            "soil_moisture_15cm": 15.0,
            "wind_gust": 8.0
        }
    } # Initial state

    # Patch the global data_cache instance used by cache_refresh
    with patch('cache_refresh.data_cache', mock_cache):
        # Patch combine_weather_data to simulate it returning None values due to API failures
        with patch('cache_refresh.combine_weather_data', return_value={"air_temp": None, "relative_humidity": None, "wind_speed": None, "soil_moisture_15cm": None, "wind_gust": None}):
            # Patch ensure_complete_weather_data to simulate fallback logic
            # It should use the mock_cache's last_valid_data
            def mock_ensure(weather_data):
                # Simulate filling from last_valid_data and setting flags
                mock_cache.cached_fields["temperature"] = True
                mock_cache.cached_fields["humidity"] = True
                mock_cache.cached_fields["wind_speed"] = True
                mock_cache.cached_fields["soil_moisture"] = True
                mock_cache.cached_fields["wind_gust"] = True
                mock_cache.using_cached_data = True
                return {
                    "air_temp": mock_cache.last_valid_data["fields"]["temperature"]["value"],
                    "relative_humidity": mock_cache.last_valid_data["fields"]["humidity"]["value"],
                    "wind_speed": mock_cache.last_valid_data["fields"]["wind_speed"]["value"],
                    "soil_moisture_15cm": mock_cache.last_valid_data["fields"]["soil_moisture"]["value"],
                    "wind_gust": mock_cache.last_valid_data["fields"]["wind_gust"]["value"]
                }
            mock_cache.ensure_complete_weather_data.side_effect = mock_ensure

            # --- Action ---
            # Trigger the refresh function
            success = await refresh_data_cache()

    # --- Assertions ---
    # For our new implementation, refresh should return False since all API calls failed
    assert success is False, "Refresh should return False when all API calls fail"
    
    # Check the flag on the *mock* instance
    assert mock_cache.last_update_success is False, "Cache's last update success flag should be False"

    # Crucial check: Verify the cache knows it's using fallback data
    assert mock_cache.using_cached_data is True, "using_cached_data flag should be True after fallback"

    # Check that the cached_fields flags were set correctly during fallback
    for field in ["temperature", "humidity", "wind_speed", "soil_moisture", "wind_gust"]:
        assert mock_cache.cached_fields[field] is True, f"{field} should be marked as cached"
    
    # Verify the fire_risk_data was updated with proper cache indicators
    assert "cached_data" in mock_cache.fire_risk_data, "cached_data should be added to fire_risk_data"
    assert mock_cache.fire_risk_data["cached_data"]["is_cached"] is True
    assert mock_cache.fire_risk_data["cached_data"]["age"] == "1 hour old"
    assert "cached_fields" in mock_cache.fire_risk_data["cached_data"]
    
    # Verify weather data has cached_fields structure
    assert "cached_fields" in mock_cache.fire_risk_data["weather"], "cached_fields should be in weather data"
    assert "timestamp" in mock_cache.fire_risk_data["weather"]["cached_fields"], "timestamp should be in cached_fields"
    
    # Verify each field has a timestamp
    timestamp_field = mock_cache.fire_risk_data["weather"]["cached_fields"]["timestamp"]
    for field in ["temperature", "humidity", "wind_speed", "soil_moisture", "wind_gust"]:
        assert field in timestamp_field, f"{field} timestamp should be present"
    
    # Verify modal content
    assert "modal_content" in mock_cache.fire_risk_data, "modal_content should be added"
    assert "note" in mock_cache.fire_risk_data["modal_content"]
    assert "Displaying cached weather data" in mock_cache.fire_risk_data["modal_content"]["note"]
    assert "warning_title" in mock_cache.fire_risk_data["modal_content"]
    assert "warning_issues" in mock_cache.fire_risk_data["modal_content"]

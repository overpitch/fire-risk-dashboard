import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from cache import DataCache, data_cache # Import the global instance
from cache_refresh import refresh_data_cache # Import the function to test
from config import TIMEZONE # Import TIMEZONE

@pytest.fixture
def cache():
    return DataCache()


def test_is_stale_no_data(cache):
    assert cache.is_stale() is True


def test_is_stale_fresh_data(cache):
    cache.last_updated = datetime.now(timezone.utc)
    assert cache.is_stale() is False


def test_is_stale_old_data(cache):
    cache.last_updated = datetime.now(timezone.utc) - timedelta(minutes=20)
    assert cache.is_stale() is True


def test_is_critically_stale_no_data(cache):
    assert cache.is_critically_stale() is True


def test_is_critically_stale_fresh_data(cache):
    cache.last_updated = datetime.now(timezone.utc)
    assert cache.is_critically_stale() is False


def test_is_critically_stale_old_data(cache):
    cache.last_updated = datetime.now(timezone.utc) - timedelta(minutes=40)  # Older than the 30-minute threshold
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
async def test_refresh_failure_sets_cached_flag(mock_synoptic, mock_wunderground):
    """
    Test that if API calls fail during refresh, the cache falls back
    and correctly sets the using_cached_data flag.
    """
    # --- Setup ---
    # Ensure there's some initial valid data in the cache
    initial_synoptic = {"stations": [{"OBSERVATIONS": {"air_temp_value_1": {"value": 10.0}}}]}
    initial_wunderground = {"KCASIERRA123": {"humidity": 50.0}}
    initial_risk = {"risk": "Low", "explanation": "Initial", "weather": {"air_temp": 10.0, "relative_humidity": 50.0}}
    
    # Use the global data_cache instance
    global_cache = data_cache 
    global_cache.update_cache(initial_synoptic, initial_wunderground, initial_risk)
    
    # Ensure the flags are initially False before the failed refresh
    global_cache.using_cached_data = False
    for field in global_cache.cached_fields:
        global_cache.cached_fields[field] = False
        
    # Simulate API failures
    mock_synoptic.return_value = None
    mock_wunderground.return_value = None
    
    # --- Action ---
    # Trigger the refresh function (which should fail)
    success = await refresh_data_cache()

    # --- Assertions ---
    assert success is False, "Refresh should indicate failure"
    assert global_cache.last_update_success is False, "Cache's last update success flag should be False"
    
    # Crucial check: Verify the cache knows it's using fallback data
    assert global_cache.using_cached_data is True, "using_cached_data flag should be True after fallback"
    
    # Check that the fire_risk_data reflects the *initial* cached data
    assert global_cache.fire_risk_data["risk"] == "Low"
    assert global_cache.fire_risk_data["weather"]["air_temp"] == 10.0
    assert global_cache.fire_risk_data["weather"]["relative_humidity"] == 50.0
    
    # Check that the cached_fields flags were set correctly during fallback
    assert global_cache.cached_fields["temperature"] is True
    assert global_cache.cached_fields["humidity"] is True
    # Add checks for other fields if necessary based on DEFAULT_VALUES or initial data

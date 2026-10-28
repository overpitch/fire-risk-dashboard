import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from cache import DataCache, data_cache # Import the global instance
from cache_refresh import refresh_data_cache # Import the function to test
from config import TIMEZONE # Import TIMEZONE

@pytest.fixture
def cache(tmp_path, monkeypatch):
    # A fresh cache for each test, run in an empty folder so it never loads
    # (or overwrites) the repository's own data/weather_cache.json
    monkeypatch.chdir(tmp_path)
    return DataCache()


def test_is_stale_no_data(cache):
    # Make sure last_updated is None to truly test this case
    cache.last_updated = None
    assert cache.is_stale() is True # Should be stale when last_updated is None


def test_is_stale_fresh_data(cache):
    cache.last_updated = datetime.now(TIMEZONE) # Use TIMEZONE
    assert cache.is_stale() is False


def test_is_stale_old_data(cache):
    cache.last_updated = datetime.now(TIMEZONE) - timedelta(minutes=30) # Use TIMEZONE
    assert cache.is_stale() is True


def test_is_critically_stale_no_data(cache):
    # A cache that has never been updated has no usable data
    assert cache.last_updated is None
    assert cache.is_critically_stale() is True


def test_is_critically_stale_fresh_data(cache):
    cache.last_updated = datetime.now(TIMEZONE) # Use TIMEZONE
    assert cache.is_critically_stale() is False


def test_is_critically_stale_old_data(cache):
    cache.last_updated = datetime.now(TIMEZONE) - timedelta(minutes=40)  # Older than the 30-minute threshold, use TIMEZONE
    assert cache.is_critically_stale() is True


def test_update_cache(cache):
    synoptic_data = {"test": "synoptic"}
    fire_risk_data = {"risk": "low"}

    cache.update_cache(synoptic_data, fire_risk_data)

    assert cache.synoptic_data == synoptic_data
    assert cache.fire_risk_data == fire_risk_data
    assert cache.last_updated is not None
    assert cache.last_valid_data["synoptic_data"] == synoptic_data
    assert cache.last_valid_data["fire_risk_data"] == fire_risk_data
    assert cache.last_valid_data["timestamp"] is not None


def test_update_cache_with_none_data(cache):
    synoptic_data = None  # Simulate missing data
    fire_risk_data = {"risk": "low"}

    cache.update_cache(synoptic_data, fire_risk_data)

    assert cache.synoptic_data is None  # Check that the None value is stored
    assert cache.fire_risk_data == fire_risk_data
    assert cache.last_updated is not None
    assert cache.last_valid_data["synoptic_data"] is None  # Check that the None value is stored
    assert cache.last_valid_data["fire_risk_data"] == fire_risk_data
    assert cache.last_valid_data["timestamp"] is not None

@pytest.mark.asyncio
async def test_wait_for_update(cache):

    # Simulate an update in a separate thread
    async def update_cache_async():
        await asyncio.sleep(0.1)  # Simulate some delay
        cache.update_cache({}, {})

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
@patch('cache_refresh.asyncio.sleep', new_callable=AsyncMock)
async def test_refresh_failure_sets_cached_flag(mock_sleep, real_cache):
    """
    If the weather API returns nothing on every attempt, the refresh fails, keeps showing
    the last good data marked as cached, and never calculates a risk or checks alerts.
    """
    cache_timestamp = datetime.now(TIMEZONE) - timedelta(hours=1)
    for field in real_cache.last_valid_data["fields"].values():
        field["timestamp"] = cache_timestamp
    real_cache.last_valid_data["timestamp"] = cache_timestamp
    real_cache.fire_risk_data = {"risk": "Orange", "explanation": "earlier", "weather": {"air_temp": 10.0}}
    real_cache.max_retries = 3

    with patch('cache_refresh.get_synoptic_data', return_value=None) as mock_synoptic, \
         patch('cache_refresh.calculate_fire_risk') as mock_calculate_fire_risk, \
         patch('cache_refresh.send_orange_to_red_alert') as mock_send_alert:
        success = await refresh_data_cache()

    assert success is False
    assert mock_synoptic.call_count == 3  # One call per attempt, then it gives up
    assert mock_sleep.await_count == 2  # It waits between attempts
    mock_calculate_fire_risk.assert_not_called()
    mock_send_alert.assert_not_called()

    assert real_cache.using_cached_data is True
    assert all(real_cache.cached_fields.values())
    assert real_cache.fire_risk_data["risk"] == "Orange"  # The last known risk is kept
    assert real_cache.fire_risk_data["cached_data"]["is_cached"] is True
    assert real_cache.fire_risk_data["cached_data"]["age"] == "1 hour"
    assert real_cache.fire_risk_data["modal_content"]["note"].startswith("Displaying cached weather data")

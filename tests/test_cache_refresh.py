import pytest
import asyncio
import itertools
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta, timezone
from cache_refresh import refresh_data_cache, schedule_next_refresh
from cache import DataCache
from api_clients import get_synoptic_data
from data_processing import combine_weather_data
from fire_risk_logic import calculate_fire_risk
# Import mocks for email/subscriber services
from unittest.mock import call


@pytest.fixture
def mock_data():
    mock_weather_data = {"STATION": []}
    mock_combined_data = {"air_temp": 25, "relative_humidity": 50, "wind_speed": 10, "soil_moisture_15cm": 20, "wind_gust": 15}
    mock_fire_risk = "low", "explanation"
    return mock_weather_data, mock_combined_data, mock_fire_risk


@pytest.mark.asyncio
async def test_refresh_data_cache_success(real_cache, fake_outside_world, mock_data):
    """A refresh stores the combined weather and the calculated risk in the cache."""
    _, mock_combined_data, _ = mock_data
    mock_calculate_fire_risk, _, _ = fake_outside_world
    mock_calculate_fire_risk.return_value = ("Orange", "explanation", RED_EFFECTIVE_VALUES)

    assert await refresh_data_cache() is True

    assert real_cache.last_updated is not None
    assert real_cache.fire_risk_data["risk"] == "Orange"
    assert real_cache.fire_risk_data["explanation"] == "explanation"
    assert real_cache.fire_risk_data["weather"]["air_temp"] == mock_combined_data["air_temp"]
    assert real_cache.previous_risk_level == "Orange"
    assert real_cache.update_in_progress is False


@pytest.mark.asyncio
@patch('cache_refresh.get_synoptic_data')
@patch('cache_refresh.format_age_string')
async def test_refresh_data_cache_api_failure(mock_format_age, mock_get_synoptic_data):
    mock_get_synoptic_data.return_value = None  # Simulate API failure
    mock_format_age.return_value = "20 minutes old"  # Mock age string formatting

    # Use a mock instance of DataCache
    mock_cache = MagicMock(spec=DataCache)
    
    # Setup mock cached data with timestamps
    now = datetime.now(timezone.utc)
    past = now - timedelta(minutes=20)
    mock_cache.last_valid_data = {
        "timestamp": past,
        "fields": {
            "temperature": {"value": 25, "timestamp": past},
            "humidity": {"value": 50, "timestamp": past},
            "wind_speed": {"value": 10, "timestamp": past},
            "soil_moisture": {"value": 20, "timestamp": past},
            "wind_gust": {"value": 15, "timestamp": past, "stations": {}}
        }
    }
    
    # Setup existing fire_risk_data to be updated
    mock_cache.fire_risk_data = {
        "risk": "low",
        "explanation": "explanation",
        "weather": {
            "air_temp": 25,
            "relative_humidity": 50,
            "wind_speed": 10,
            "soil_moisture_15cm": 20,
            "wind_gust": 15
        }
    }
    
    mock_cache.update_in_progress = False
    mock_cache.reset_update_event = MagicMock()
    mock_cache.max_retries = 3
    mock_cache.update_timeout = 10
    mock_cache.retry_delay = 5
    mock_cache.cached_fields = {
        "temperature": False,
        "humidity": False,
        "wind_speed": False,
        "soil_moisture": False,
        "wind_gust": False
    }
    
    # Patch the config logger to check warnings
    with patch('cache_refresh.logger') as mock_logger:
        # Patch the global data_cache instance
        with patch('cache_refresh.data_cache', mock_cache):
            # Setup expected combine_weather_data mock
            with patch('cache_refresh.combine_weather_data') as mock_combine:
                # In the real implementation, the function returns True on success
                # even if it uses cached data, which matches our modified code
                mock_combine.return_value = {
                    "air_temp": None,
                    "relative_humidity": None,
                    "wind_speed": None,
                    "soil_moisture_15cm": None,
                    "wind_gust": None
                }
                
                # Run the function under test
                with patch('cache_refresh.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                    result = await refresh_data_cache()
                assert result is False
                
                # Each attempt fails without data, with a wait between attempts
                assert mock_get_synoptic_data.call_count == 3
                assert mock_sleep.await_count == 2
                mock_combine.assert_not_called()
                
                # Verify error logging
                mock_logger.error.assert_any_call("All data refresh attempts failed")
            
    # Verify cache markers were properly set
    assert mock_cache.using_cached_data is True
    
    # Verify all fields are marked as cached
    for field in mock_cache.cached_fields:
        assert mock_cache.cached_fields[field] is True
        
    # Verify fire_risk_data was updated with proper cache markers
    assert "cached_data" in mock_cache.fire_risk_data
    assert mock_cache.fire_risk_data["cached_data"]["is_cached"] is True
    assert mock_cache.fire_risk_data["cached_data"]["age"] == "20 minutes old"
    
    # Verify weather data has proper cache structure
    assert "cached_fields" in mock_cache.fire_risk_data["weather"]
    assert "timestamp" in mock_cache.fire_risk_data["weather"]["cached_fields"]
    
    # Verify modal content was added
    assert "modal_content" in mock_cache.fire_risk_data
    assert "note" in mock_cache.fire_risk_data["modal_content"]
    assert "Displaying cached weather data" in mock_cache.fire_risk_data["modal_content"]["note"]


@pytest.mark.asyncio
@patch('cache_refresh.asyncio.sleep', new_callable=AsyncMock)
async def test_refresh_data_cache_retry(mock_sleep, real_cache, fake_outside_world, mock_data):
    """If processing fails once, the refresh waits and tries again."""
    _, mock_combined_data, _ = mock_data
    mock_calculate_fire_risk, _, _ = fake_outside_world
    mock_calculate_fire_risk.return_value = ("Orange", "explanation", RED_EFFECTIVE_VALUES)
    real_cache.max_retries = 2

    with patch('cache_refresh.combine_weather_data',
               side_effect=[ValueError("First attempt should fail"), dict(mock_combined_data)]) as mock_combine:
        assert await refresh_data_cache() is True

    assert mock_combine.call_count == 2
    mock_sleep.assert_awaited_once_with(real_cache.retry_delay)
    assert real_cache.fire_risk_data["risk"] == "Orange"


@pytest.mark.asyncio
@patch('cache_refresh.asyncio.sleep', new_callable=AsyncMock)
async def test_refresh_data_cache_gives_up_after_max_retries(mock_sleep, real_cache, fake_outside_world):
    """If every attempt fails, the refresh reports failure and marks all fields as cached."""
    real_cache.max_retries = 2

    with patch('cache_refresh.combine_weather_data', side_effect=ValueError("always fails")) as mock_combine:
        assert await refresh_data_cache() is False

    assert mock_combine.call_count == 2
    assert real_cache.using_cached_data is True
    assert all(real_cache.cached_fields.values())


@pytest.mark.asyncio
@patch('cache_refresh.get_synoptic_data')
@patch('cache_refresh.asyncio.sleep', new_callable=AsyncMock)
async def test_refresh_data_cache_timeout(mock_sleep, mock_get_synoptic_data):
    # Use AsyncMock objects with side_effect to simulate long API calls
    # This creates a coroutine that needs to be awaited
    async def slow_api_call():
        await asyncio.sleep(0.1)
        return None
        
    mock_get_synoptic_data.side_effect = slow_api_call

    # Use a mock instance of DataCache
    mock_cache = MagicMock(spec=DataCache)
    mock_cache.update_timeout = 0.01  # Set a very short timeout
    mock_cache.update_in_progress = False
    mock_cache.reset_update_event = MagicMock()
    mock_cache.max_retries = 3
    mock_cache.retry_delay = 5
    mock_cache.cached_fields = {}
    # Add fire_risk_data attribute to fix AttributeError
    mock_cache.fire_risk_data = {"risk": "low", "explanation": "test", "weather": {}}
    
    # Add last_valid_data attribute to fix AttributeError
    now = datetime.now(timezone.utc)
    mock_cache.last_valid_data = {
        "timestamp": now,
        "fields": {
            "temperature": {"value": 25, "timestamp": now},
            "humidity": {"value": 50, "timestamp": now},
            "wind_speed": {"value": 10, "timestamp": now},
            "soil_moisture": {"value": 20, "timestamp": now},
            "wind_gust": {"value": 15, "timestamp": now, "stations": {}}
        }
    }
    
    # Patch the global data_cache instance
    with patch('cache_refresh.data_cache', mock_cache):
        # Mock time.time() to simulate time passing during the test
        clock = itertools.count(0, 0.02)
        with patch('time.time', side_effect=lambda: next(clock)):  # Increasing times that never run out
            assert await refresh_data_cache() is False
            
    # Verify sleep was not awaited
    mock_sleep.assert_not_awaited()


@pytest.mark.asyncio
@patch('cache_refresh.get_synoptic_data')
@patch('cache_refresh.format_age_string')
async def test_refresh_data_cache_cached_data(mock_format_age, mock_get_synoptic_data, mock_data):
    mock_weather_data, mock_combined_data, mock_fire_risk = mock_data
    mock_format_age.return_value = "20 minutes old"  # Mock age string formatting

    mock_get_synoptic_data.return_value = None

    # Create a mock DataCache instance
    mock_cache = MagicMock(spec=DataCache)
    mock_cache.update_in_progress = False
    mock_cache.reset_update_event = MagicMock()
    mock_cache.max_retries = 3
    mock_cache.update_timeout = 10
    mock_cache.retry_delay = 5
    mock_cache.cached_fields = {
        "temperature": False,
        "humidity": False,
        "wind_speed": False,
        "soil_moisture": False,
        "wind_gust": False
    }
    
    # Populate mock cache with initial data
    now = datetime.now(timezone.utc)
    past = now - timedelta(minutes=20)
    
    # Setup cached data with valid values that should be used when API calls fail
    mock_cache.last_valid_data = {
        "fields": {
            "temperature": {"value": 26, "timestamp": past},
            "humidity": {"value": 11, "timestamp": past},
            "wind_speed": {"value": 21, "timestamp": past},
            "soil_moisture": {"value": 1, "timestamp": past},
            "wind_gust": {"value": 16, "timestamp": past, "stations": {}}
        },
        "synoptic_data": mock_weather_data,
        "fire_risk_data": {"risk": "moderate"},
        "timestamp": past,
        "weather": {
            "air_temp": 26,
            "relative_humidity": 11,
            "wind_speed": 21,
            "soil_moisture_15cm": 1,
            "wind_gust": 16
        }
    }
    
    # Setup expected cached risk data
    mock_cache.fire_risk_data = {
        "risk": "moderate",
        "weather": {
            "air_temp": 26,
            "relative_humidity": 11,
            "wind_speed": 21,
            "soil_moisture_15cm": 1,
            "wind_gust": 16
        }
    }
    
    # Patch the global data_cache instance
    with patch('cache_refresh.data_cache', mock_cache):
        with patch('cache_refresh.combine_weather_data') as mock_combine:
            # Configure combine_weather_data to return data with None values
            # which will trigger the cache fallback
            mock_combine.return_value = {
                "air_temp": None,
                "relative_humidity": None,
                "wind_speed": None,
                "soil_moisture_15cm": None,
                "wind_gust": None
            }
            
            # Our new implementation returns False when all API calls fail
            with patch('cache_refresh.asyncio.sleep', new_callable=AsyncMock):
                assert await refresh_data_cache() is False

        # Verify cache state after refresh
        assert mock_cache.using_cached_data is True
        
        # Verify all fields are marked as cached
        for field in mock_cache.cached_fields:
            assert mock_cache.cached_fields[field] is True
            
        # Verify the fire_risk_data was updated with proper cache indicators
        assert "cached_data" in mock_cache.fire_risk_data
        assert mock_cache.fire_risk_data["cached_data"]["is_cached"] is True
        assert mock_cache.fire_risk_data["cached_data"]["age"] == "20 minutes old"
        
        # Verify weather data has cached_fields structure
        assert "cached_fields" in mock_cache.fire_risk_data["weather"]
        assert "timestamp" in mock_cache.fire_risk_data["weather"]["cached_fields"]
        
        # Verify modal content was added
        assert "modal_content" in mock_cache.fire_risk_data
        assert "note" in mock_cache.fire_risk_data["modal_content"]
        assert "Displaying cached weather data" in mock_cache.fire_risk_data["modal_content"]["note"]


@pytest.mark.asyncio
@patch('cache_refresh.refresh_data_cache')
async def test_schedule_next_refresh_exception(mock_refresh_data_cache, caplog):
    mock_refresh_data_cache.side_effect = Exception("Test Exception")
    
    # Use a mock instance of DataCache
    mock_cache = MagicMock(spec=DataCache)
    mock_cache.refresh_task_active = True
    
    # Patch the global data_cache instance
    with patch('cache_refresh.data_cache', mock_cache):
        await schedule_next_refresh(0.01)
        
        # The actual error message is "Error in scheduled refresh: Test Exception"
        assert "Error in scheduled refresh: Test Exception" in caplog.text
        assert mock_cache.refresh_task_active is False


# --- Tests for Orange-to-Red Alert Logic ---
# These use a real DataCache (disk I/O disabled) so the real alert rule and risk-level
# tracking run; only the weather API, risk calculation, subscribers and email are faked.

RED_EFFECTIVE_VALUES = {"temperature": 90.0, "humidity": 8.0, "wind_speed": 20.0,
                        "wind_gust": 28.0, "soil_moisture": 5.0}


@pytest.fixture
def fake_outside_world(mock_data):
    """Fake weather API, data combination, risk calculation, subscribers and email sending."""
    mock_weather_data, mock_combined_data, _ = mock_data
    with patch('cache_refresh.get_synoptic_data', return_value=mock_weather_data), \
         patch('cache_refresh.combine_weather_data', side_effect=lambda *a, **k: dict(mock_combined_data)), \
         patch('cache_refresh.calculate_fire_risk') as mock_calculate_fire_risk, \
         patch('cache_refresh.get_active_subscribers') as mock_get_subscribers, \
         patch('cache_refresh.send_orange_to_red_alert', return_value="mock-message-id") as mock_send_alert:
        yield mock_calculate_fire_risk, mock_get_subscribers, mock_send_alert


@pytest.mark.asyncio
async def test_refresh_data_cache_orange_to_red_alert_sent(real_cache, fake_outside_world):
    """An Orange -> Red transition emails all active subscribers once, with the values used for the risk."""
    mock_calculate_fire_risk, mock_get_subscribers, mock_send_alert = fake_outside_world
    test_subscribers = ["test1@example.com", "test2@example.com"]
    mock_calculate_fire_risk.return_value = ("Red", "Conditions extremely dry and windy", RED_EFFECTIVE_VALUES)
    mock_get_subscribers.return_value = {"subscribers": test_subscribers}
    real_cache.update_risk_level("Orange")

    assert await refresh_data_cache() is True

    mock_send_alert.assert_called_once()
    sent_recipients, sent_weather_data = mock_send_alert.call_args.args[:2]
    assert sent_recipients == test_subscribers
    assert sent_weather_data == {
        'temperature': "90.0°F",
        'humidity': "8.0%",
        'wind_speed': "20.0 mph",
        'wind_gust': "28.0 mph",
        'soil_moisture': "5.0%",
    }
    assert real_cache.previous_risk_level == "Red"
    assert real_cache.last_alerted_timestamp is not None
    assert real_cache.fire_risk_data["risk"] == "Red"


@pytest.mark.asyncio
async def test_refresh_data_cache_orange_to_red_alert_sent_only_once(real_cache, fake_outside_world):
    """Staying Red on the next refresh must not send a second alert."""
    mock_calculate_fire_risk, mock_get_subscribers, mock_send_alert = fake_outside_world
    mock_calculate_fire_risk.return_value = ("Red", "dry", RED_EFFECTIVE_VALUES)
    mock_get_subscribers.return_value = {"subscribers": ["test1@example.com"]}
    real_cache.update_risk_level("Orange")

    assert await refresh_data_cache() is True
    assert await refresh_data_cache() is True

    mock_send_alert.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_data_cache_orange_to_red_no_subscribers(real_cache, fake_outside_world):
    """Orange -> Red with no active subscribers sends nothing but still records the new risk level."""
    mock_calculate_fire_risk, mock_get_subscribers, mock_send_alert = fake_outside_world
    mock_calculate_fire_risk.return_value = ("Red", "dry", RED_EFFECTIVE_VALUES)
    mock_get_subscribers.return_value = {"subscribers": []}
    real_cache.update_risk_level("Orange")

    assert await refresh_data_cache() is True

    mock_get_subscribers.assert_called_once()
    mock_send_alert.assert_not_called()
    assert real_cache.previous_risk_level == "Red"
    assert real_cache.last_email_send_outcome == "not_triggered_no_recipients"


@pytest.mark.asyncio
@pytest.mark.parametrize("prev_risk, new_risk", [
    ("Green", "Orange"),
    ("Orange", "Orange"),
    ("Red", "Orange"),
    ("Red", "Red"),
    ("Green", "Red"), # Test non-Orange start
])
async def test_refresh_data_cache_no_alert_on_other_transitions(real_cache, fake_outside_world, prev_risk, new_risk):
    """Only Orange -> Red alerts; every other transition just records the new risk level."""
    mock_calculate_fire_risk, mock_get_subscribers, mock_send_alert = fake_outside_world
    mock_calculate_fire_risk.return_value = (new_risk, "Some reason", RED_EFFECTIVE_VALUES)
    real_cache.update_risk_level(prev_risk)

    assert await refresh_data_cache() is True

    mock_get_subscribers.assert_not_called() # Should not even check subscribers
    mock_send_alert.assert_not_called()
    assert real_cache.previous_risk_level == new_risk


@pytest.mark.asyncio
@patch('cache_refresh.refresh_data_cache')
async def test_schedule_next_refresh(mock_refresh_data_cache):
    mock_refresh_data_cache.return_value = True

    # Use a mock instance of DataCache
    mock_cache = MagicMock(spec=DataCache)
    mock_cache.refresh_task_active = True
    
    # Patch the global data_cache instance
    with patch('cache_refresh.data_cache', mock_cache):
        with patch('cache_refresh.logger') as mock_logger:
            await schedule_next_refresh(0.01)  # Schedule refresh after a short delay
            mock_logger.info.assert_called_with("Scheduling next background refresh in 0.01 minutes")
            
        mock_refresh_data_cache.assert_awaited_once()
        assert mock_cache.refresh_task_active is False

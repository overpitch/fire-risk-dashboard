import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta, timezone
from cache_refresh import refresh_data_cache, schedule_next_refresh
from cache import DataCache
from api_clients import get_synoptic_data
# Mock for the removed get_wunderground_data function
from tests.conftest import get_wunderground_data
from data_processing import combine_weather_data
from fire_risk_logic import calculate_fire_risk
# Import mocks for email/subscriber services
from unittest.mock import call


@pytest.fixture
def mock_data():
    mock_weather_data = {"STATION": []}
    mock_wunderground_data = {"observations": []}
    mock_combined_data = {"air_temp": 25, "relative_humidity": 50, "wind_speed": 10, "soil_moisture_15cm": 20, "wind_gust": 15}
    mock_fire_risk = "low", "explanation"
    return mock_weather_data, mock_wunderground_data, mock_combined_data, mock_fire_risk


@pytest.mark.asyncio
@patch('cache_refresh.get_synoptic_data')
@patch('cache_refresh.get_wunderground_data')
@patch('cache_refresh.combine_weather_data')
@patch('cache_refresh.calculate_fire_risk')
async def test_refresh_data_cache_success(mock_calculate_fire_risk, mock_combine_weather_data, mock_get_wunderground_data, mock_get_synoptic_data, mock_data):
    mock_weather_data, mock_wunderground_data, mock_combined_data, mock_fire_risk = mock_data

    mock_get_synoptic_data.return_value = mock_weather_data
    mock_get_wunderground_data.return_value = mock_wunderground_data
    mock_combine_weather_data.return_value = mock_combined_data
    mock_calculate_fire_risk.return_value = mock_fire_risk

    # Create a risk data object with the expected structure
    risk_data = {"risk": "low", "explanation": "explanation", "weather": mock_combined_data}
    
    # Use a mock instance of DataCache instead of the class
    mock_cache = MagicMock(spec=DataCache)
    mock_cache.fire_risk_data = risk_data
    mock_cache.update_in_progress = False
    mock_cache.reset_update_event = MagicMock()
    mock_cache.max_retries = 3
    mock_cache.update_timeout = 10
    mock_cache.retry_delay = 5
    mock_cache.cached_fields = {}
    mock_cache.previous_risk_level = "Green" # Default previous risk

    # Patch the global data_cache instance
    with patch('cache_refresh.data_cache', mock_cache):
        # Run the test
        assert await refresh_data_cache() is True
        mock_cache.update_cache.assert_called_once()
        assert mock_cache.fire_risk_data["risk"] == "low" # Risk calculated
        assert mock_cache.previous_risk_level == "low" # Previous risk updated
        assert mock_cache.last_update_success is True


@pytest.mark.asyncio
@patch('cache_refresh.get_synoptic_data')
@patch('cache_refresh.get_wunderground_data')
@patch('cache_refresh.format_age_string')
async def test_refresh_data_cache_api_failure(mock_format_age, mock_get_wunderground_data, mock_get_synoptic_data):
    mock_get_synoptic_data.return_value = None  # Simulate API failure
    mock_get_wunderground_data.return_value = None
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
                result = await refresh_data_cache()
                assert result is False
                
                # Verify error logging
                mock_logger.error.assert_any_call("All data refresh attempts failed")
                
                # Check that the warning was logged
                mock_logger.warning.assert_any_call("Data refresh taking too long (over 10s), aborting")
            
    # Verify cache markers were properly set
    assert mock_cache.last_update_success is False
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
@patch('cache_refresh.get_synoptic_data')
@patch('cache_refresh.get_wunderground_data')
@patch('cache_refresh.asyncio.sleep', new_callable=AsyncMock)  # Mock asyncio.sleep
async def test_refresh_data_cache_retry(mock_sleep, mock_get_wunderground_data, mock_get_synoptic_data, mock_data):
    mock_weather_data, mock_wunderground_data, mock_combined_data, mock_fire_risk = mock_data

    # Set up normal API returns
    mock_get_synoptic_data.return_value = mock_weather_data
    mock_get_wunderground_data.return_value = mock_wunderground_data
    
    with patch('cache_refresh.combine_weather_data') as mock_combine:
        with patch('cache_refresh.calculate_fire_risk') as mock_calc:
            # First attempt with combine_weather_data raises an exception, second succeeds
            def combine_side_effect(*args, **kwargs):
                if not hasattr(combine_side_effect, 'called'):
                    combine_side_effect.called = True
                    raise ValueError("First attempt should fail")
                return mock_combined_data
            
            mock_combine.side_effect = combine_side_effect
            mock_calc.return_value = mock_fire_risk
            
            # Create a risk data object with the expected structure
            risk_data = {"risk": "low", "explanation": "explanation", "weather": mock_combined_data}
            
            # Use a mock instance of DataCache
            mock_cache = MagicMock(spec=DataCache)
            mock_cache.fire_risk_data = risk_data
            mock_cache.max_retries = 2
            mock_cache.retry_delay = 0.01
            mock_cache.update_in_progress = False
            mock_cache.reset_update_event = MagicMock()
            mock_cache.update_timeout = 10
            mock_cache.cached_fields = {}
            
            # Patch the global data_cache instance
            with patch('cache_refresh.data_cache', mock_cache):
                assert await refresh_data_cache() is True
                mock_cache.update_cache.assert_called_once()
                assert mock_cache.fire_risk_data["risk"] == "low"
                mock_sleep.assert_awaited_once()  # Check if asyncio.sleep was called


@pytest.mark.asyncio
@patch('cache_refresh.get_synoptic_data')
@patch('cache_refresh.get_wunderground_data')
@patch('cache_refresh.asyncio.sleep', new_callable=AsyncMock)
async def test_refresh_data_cache_timeout(mock_sleep, mock_get_wunderground_data, mock_get_synoptic_data):
    # Use AsyncMock objects with side_effect to simulate long API calls
    # This creates a coroutine that needs to be awaited
    async def slow_api_call():
        await asyncio.sleep(0.1)
        return None
        
    mock_get_synoptic_data.side_effect = slow_api_call
    mock_get_wunderground_data.side_effect = slow_api_call

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
        with patch('time.time', side_effect=[0, 0.02, 0.03]):  # Returns increasing times
            assert await refresh_data_cache() is False
            
    # Verify sleep was not awaited
    mock_sleep.assert_not_awaited()


@pytest.mark.asyncio
@patch('cache_refresh.get_synoptic_data')
@patch('cache_refresh.get_wunderground_data')
@patch('cache_refresh.format_age_string')
async def test_refresh_data_cache_cached_data(mock_format_age, mock_get_wunderground_data, mock_get_synoptic_data, mock_data):
    mock_weather_data, mock_wunderground_data, mock_combined_data, mock_fire_risk = mock_data
    mock_format_age.return_value = "20 minutes old"  # Mock age string formatting

    mock_get_synoptic_data.return_value = None
    mock_get_wunderground_data.return_value = None

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
        "wunderground_data": mock_wunderground_data,
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
            assert await refresh_data_cache() is False

        # Verify cache state after refresh
        assert mock_cache.last_update_success is False
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

@pytest.mark.asyncio
@patch('cache_refresh.get_synoptic_data')
@patch('cache_refresh.combine_weather_data')
@patch('cache_refresh.calculate_fire_risk')
@patch('cache_refresh.get_active_subscribers')
@patch('cache_refresh.send_orange_to_red_alert')
async def test_refresh_data_cache_orange_to_red_alert_sent(
    mock_send_alert, mock_get_subscribers, mock_calculate_fire_risk,
    mock_combine_weather_data, mock_get_synoptic_data, mock_data
):
    """Test that alert is sent on Orange -> Red transition with subscribers."""
    mock_weather_data, _, mock_combined_data, _ = mock_data
    test_subscribers = ["test1@example.com", "test2@example.com"]
    risk_explanation = "Conditions extremely dry and windy"

    # Setup mocks
    mock_get_synoptic_data.return_value = mock_weather_data
    mock_combine_weather_data.return_value = mock_combined_data
    mock_calculate_fire_risk.return_value = ("Red", risk_explanation) # New risk is Red
    mock_get_subscribers.return_value = test_subscribers
    mock_send_alert.return_value = "mock-message-id" # Simulate successful send

    # Configure mock cache
    mock_cache = MagicMock(spec=DataCache)
    mock_cache.update_in_progress = False
    mock_cache.reset_update_event = MagicMock()
    mock_cache.max_retries = 1
    mock_cache.update_timeout = 10
    mock_cache.retry_delay = 1
    mock_cache.cached_fields = {}
    mock_cache.previous_risk_level = "Orange" # CRITICAL: Previous risk was Orange
    mock_cache.fire_risk_data = {"risk": "Orange"} # Initial state

    # Patch the global data_cache instance and logger
    with patch('cache_refresh.data_cache', mock_cache), \
         patch('cache_refresh.logger') as mock_logger:
        # Run the refresh
        result = await refresh_data_cache()

        # Assertions
        assert result is True # Refresh itself should succeed
        mock_get_subscribers.assert_called_once()
        mock_send_alert.assert_called_once()

        # Check arguments passed to send_orange_to_red_alert
        call_args, call_kwargs = mock_send_alert.call_args
        sent_recipients = call_args[0]
        sent_weather_data = call_args[1]

        assert sent_recipients == test_subscribers
        # Check if weather data was formatted correctly (based on cache_refresh logic)
        assert sent_weather_data['temperature'] == f"{mock_combined_data.get('air_temp', 'N/A')}°C"
        assert sent_weather_data['humidity'] == f"{mock_combined_data.get('relative_humidity', 'N/A')}%"
        assert sent_weather_data['wind_speed'] == f"{mock_combined_data.get('wind_speed', 'N/A')} mph"
        assert sent_weather_data['wind_gust'] == f"{mock_combined_data.get('wind_gust', 'N/A')} mph"
        assert sent_weather_data['soil_moisture'] == f"{mock_combined_data.get('soil_moisture_15cm', 'N/A')}%"

        # Check logs
        mock_logger.info.assert_any_call(f"Risk transition detected: Orange -> Red. Preparing alert.")
        mock_logger.info.assert_any_call(f"Found {len(test_subscribers)} active subscribers for the alert.")
        mock_logger.info.assert_any_call(f"Orange-to-Red alert email sent successfully to {len(test_subscribers)} subscribers. Message ID: mock-message-id")

        # Verify cache update
        mock_cache.update_cache.assert_called_once()
        # Check that previous_risk_level was updated *after* the check
        assert mock_cache.previous_risk_level == "Red"


@pytest.mark.asyncio
@patch('cache_refresh.get_synoptic_data')
@patch('cache_refresh.combine_weather_data')
@patch('cache_refresh.calculate_fire_risk')
@patch('cache_refresh.get_active_subscribers')
@patch('cache_refresh.send_orange_to_red_alert')
async def test_refresh_data_cache_orange_to_red_no_subscribers(
    mock_send_alert, mock_get_subscribers, mock_calculate_fire_risk,
    mock_combine_weather_data, mock_get_synoptic_data, mock_data
):
    """Test Orange -> Red transition when no subscribers are found."""
    mock_weather_data, _, mock_combined_data, _ = mock_data
    risk_explanation = "Conditions extremely dry and windy"

    # Setup mocks
    mock_get_synoptic_data.return_value = mock_weather_data
    mock_combine_weather_data.return_value = mock_combined_data
    mock_calculate_fire_risk.return_value = ("Red", risk_explanation)
    mock_get_subscribers.return_value = [] # No subscribers

    # Configure mock cache
    mock_cache = MagicMock(spec=DataCache)
    mock_cache.update_in_progress = False
    mock_cache.reset_update_event = MagicMock()
    mock_cache.max_retries = 1
    mock_cache.update_timeout = 10
    mock_cache.retry_delay = 1
    mock_cache.cached_fields = {}
    mock_cache.previous_risk_level = "Orange"
    mock_cache.fire_risk_data = {"risk": "Orange"}

    # Patch the global data_cache instance and logger
    with patch('cache_refresh.data_cache', mock_cache), \
         patch('cache_refresh.logger') as mock_logger:
        # Run the refresh
        result = await refresh_data_cache()

        # Assertions
        assert result is True
        mock_get_subscribers.assert_called_once()
        mock_send_alert.assert_not_called() # Alert should NOT be sent

        # Check logs
        mock_logger.info.assert_any_call(f"Risk transition detected: Orange -> Red. Preparing alert.")
        mock_logger.warning.assert_any_call("Orange-to-Red transition detected, but no active subscribers found.")

        # Verify cache update
        mock_cache.update_cache.assert_called_once()
        assert mock_cache.previous_risk_level == "Red"


@pytest.mark.asyncio
@pytest.mark.parametrize("prev_risk, new_risk", [
    ("Green", "Orange"),
    ("Orange", "Orange"),
    ("Red", "Orange"),
    ("Red", "Red"),
    ("Green", "Red"), # Test non-Orange start
])
@patch('cache_refresh.get_synoptic_data')
@patch('cache_refresh.combine_weather_data')
@patch('cache_refresh.calculate_fire_risk')
@patch('cache_refresh.get_active_subscribers')
@patch('cache_refresh.send_orange_to_red_alert')
async def test_refresh_data_cache_no_alert_on_other_transitions(
    mock_send_alert, mock_get_subscribers, mock_calculate_fire_risk,
    mock_combine_weather_data, mock_get_synoptic_data, mock_data,
    prev_risk, new_risk
):
    """Test that alert is NOT sent for transitions other than Orange -> Red."""
    mock_weather_data, _, mock_combined_data, _ = mock_data
    risk_explanation = "Some reason"

    # Setup mocks
    mock_get_synoptic_data.return_value = mock_weather_data
    mock_combine_weather_data.return_value = mock_combined_data
    mock_calculate_fire_risk.return_value = (new_risk, risk_explanation)

    # Configure mock cache
    mock_cache = MagicMock(spec=DataCache)
    mock_cache.update_in_progress = False
    mock_cache.reset_update_event = MagicMock()
    mock_cache.max_retries = 1
    mock_cache.update_timeout = 10
    mock_cache.retry_delay = 1
    mock_cache.cached_fields = {}
    mock_cache.previous_risk_level = prev_risk # Set previous risk from parameter
    mock_cache.fire_risk_data = {"risk": prev_risk}

    # Patch the global data_cache instance
    with patch('cache_refresh.data_cache', mock_cache):
        # Run the refresh
        result = await refresh_data_cache()

        # Assertions
        assert result is True
        mock_get_subscribers.assert_not_called() # Should not even check subscribers
        mock_send_alert.assert_not_called()     # Alert should definitely not be sent

        # Verify cache update
        mock_cache.update_cache.assert_called_once()
        assert mock_cache.previous_risk_level == new_risk # Previous risk updated to new risk


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

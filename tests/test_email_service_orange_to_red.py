import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta, timezone
from cache_refresh import refresh_data_cache
from cache import DataCache
from email_service import send_test_email


@pytest.mark.asyncio
@patch('cache_refresh.send_test_email')
@patch('cache_refresh.get_synoptic_data')
@patch('cache_refresh.combine_weather_data')
@patch('cache_refresh.calculate_fire_risk')
async def test_orange_to_red_alert_email(mock_calculate_fire_risk, mock_combine_weather_data, 
                                        mock_get_synoptic_data, mock_send_test_email):
    """Test that an email is sent when risk level transitions from Orange to Red."""
    
    # Mock weather data and API calls
    mock_weather_data = {"STATION": []}
    mock_get_synoptic_data.return_value = mock_weather_data
    
    # Mock combined weather data
    mock_combined_data = {
        "air_temp": 30, 
        "relative_humidity": 10, 
        "wind_speed": 20, 
        "soil_moisture_15cm": 5, 
        "wind_gust": 25
    }
    mock_combine_weather_data.return_value = mock_combined_data
    
    # Mock fire risk calculation to return "Red"
    mock_calculate_fire_risk.return_value = ("Red", "High fire risk due to all thresholds being exceeded.")
    
    # Create a mock DataCache instance with previous_risk_level set to "Orange"
    mock_cache = MagicMock(spec=DataCache)
    mock_cache.update_in_progress = False
    mock_cache.reset_update_event = MagicMock()
    mock_cache.max_retries = 3
    mock_cache.update_timeout = 10
    mock_cache.retry_delay = 0
    mock_cache.cached_fields = {}
    mock_cache.previous_risk_level = "Orange"  # Set previous risk level to Orange
    
    # Patch the global data_cache instance
    with patch('cache_refresh.data_cache', mock_cache):
        # Run the refresh function
        assert await refresh_data_cache() is True
        
        # Verify email was sent with correct parameters
        mock_send_test_email.assert_called_once()
        
        # Extract the call arguments
        call_args = mock_send_test_email.call_args[1]
        
        # Verify the email parameters
        assert call_args['sender'] == "advisory@scfireweather.org"
        assert call_args['recipient'] == "info@scfireweather.org"
        assert "Fire Risk Alert: Level Increased to RED" in call_args['subject']
        
        # Verify the email body contains the key information
        assert "increased from Orange to RED" in call_args['body_text']
        assert "Temperature: 30°C" in call_args['body_text']
        assert "Humidity: 10%" in call_args['body_text']
        assert "Wind Speed: 20 mph" in call_args['body_text']
        assert "Wind Gusts: 25 mph" in call_args['body_text']
        assert "Soil Moisture (15cm): 5%" in call_args['body_text']
        
        # Verify the previous_risk_level was updated to "Red"
        assert mock_cache.previous_risk_level == "Red"


@pytest.mark.asyncio
@patch('cache_refresh.send_test_email')
@patch('cache_refresh.get_synoptic_data')
@patch('cache_refresh.combine_weather_data')
@patch('cache_refresh.calculate_fire_risk')
async def test_no_email_for_other_transitions(mock_calculate_fire_risk, mock_combine_weather_data,
                                             mock_get_synoptic_data, mock_send_test_email):
    """Test that no email is sent for transitions other than Orange to Red."""
    
    # Test cases for different transitions that should NOT trigger emails
    test_cases = [
        ("Orange", "Orange"),  # No change
        ("Red", "Red"),        # No change
        ("Red", "Orange"),     # Red to Orange (improvement)
        (None, "Orange"),      # First initialization to Orange
        (None, "Red"),         # First initialization to Red
    ]
    
    # Mock weather data and API calls
    mock_weather_data = {"STATION": []}
    mock_get_synoptic_data.return_value = mock_weather_data
    
    # Mock combined weather data
    mock_combined_data = {
        "air_temp": 30,
        "relative_humidity": 10,
        "wind_speed": 20,
        "soil_moisture_15cm": 5,
        "wind_gust": 25
    }
    mock_combine_weather_data.return_value = mock_combined_data
    
    for prev_risk, new_risk in test_cases:
        # Reset the mock
        mock_send_test_email.reset_mock()
        
        # Mock fire risk calculation to return the new risk level
        mock_calculate_fire_risk.return_value = (new_risk, f"Test risk level: {new_risk}")
        
        # Create a mock DataCache instance with specified previous_risk_level
        mock_cache = MagicMock(spec=DataCache)
        mock_cache.update_in_progress = False
        mock_cache.reset_update_event = MagicMock()
        mock_cache.max_retries = 3
        mock_cache.update_timeout = 10
        mock_cache.retry_delay = 0
        mock_cache.cached_fields = {}
        mock_cache.previous_risk_level = prev_risk  # Set previous risk level
        
        # Patch the global data_cache instance
        with patch('cache_refresh.data_cache', mock_cache):
            # Run the refresh function
            assert await refresh_data_cache() is True
            
            # Verify email was NOT sent
            mock_send_test_email.assert_not_called()
            
            # Verify the previous_risk_level was updated
            assert mock_cache.previous_risk_level == new_risk

import unittest
from unittest.mock import patch, MagicMock
import asyncio
from datetime import datetime, timedelta
import pytest

from cache import DataCache
from config import TIMEZONE
from cache_refresh import refresh_data_cache


class TestOrangeToRedAlertCalendarLimitIntegration(unittest.TestCase):
    """Integration tests for the Orange to Red alert calendar day limit feature."""

    @patch('cache_refresh.get_active_subscribers')
    @patch('cache_refresh.send_orange_to_red_alert')
    @patch('cache_refresh.calculate_fire_risk')
    @patch('cache_refresh.get_synoptic_data')
    @patch('cache_refresh.data_cache')
    def test_multiple_transitions_same_day(self, mock_data_cache, mock_get_synoptic_data,
                                          mock_calculate_risk, mock_send_alert,
                                          mock_get_subscribers):
        """Test multiple Orange to Red transitions on the same day - only first triggers email."""
        # Set up required mock attributes
        current_time = datetime.now(TIMEZONE)
        mock_data_cache.update_in_progress = False
        mock_data_cache.previous_risk_level = "Orange"
        mock_data_cache.risk_level_timestamp = current_time - timedelta(hours=3)
        mock_data_cache.last_alerted_timestamp = current_time - timedelta(hours=2)
        mock_data_cache.max_retries = 5
        mock_data_cache.retry_delay = 0
        mock_data_cache.update_timeout = 15
        mock_data_cache.refresh_task_active = False
        mock_data_cache.using_cached_data = False
        mock_data_cache.cached_fields = {"temperature": False, "humidity": False, "wind_speed": False, "soil_moisture": False}
        
        # Mock the methods
        mock_data_cache.reset_update_event = MagicMock()
        mock_data_cache.update_cache = MagicMock()
        # First call should return False (alert already sent today)
        mock_data_cache.should_send_alert_for_transition = MagicMock(return_value=False)
        mock_data_cache.record_alert_sent = MagicMock()
        mock_data_cache.update_risk_level = MagicMock()
        mock_data_cache.ensure_complete_weather_data.return_value = {
            "air_temp": 32,
            "relative_humidity": 12,
            "wind_speed": 25,
            "wind_gust": 35,
            "soil_moisture_15cm": 8
        }
        
        # Mock API data
        mock_get_synoptic_data.return_value = {"data": "sample"}
        
        # Mock calculating risk level to Red (would normally trigger an alert)
        mock_calculate_risk.return_value = ("Red", "High temperature and low humidity")
        
        # Mock subscribers list
        mock_get_subscribers.return_value = {"subscribers": ["test@example.com"]}
        
        # Set up the async function to be called synchronously
        async def run_refresh():
            return await refresh_data_cache()
            
        # Run the async function in an event loop
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(run_refresh())
        finally:
            loop.close()
        
        # Verify the results
        self.assertTrue(result)  # Refresh should be successful
        mock_get_subscribers.assert_not_called()  # Should NOT try to get subscribers
        mock_send_alert.assert_not_called()  # Should NOT try to send an alert
        
        # Verify our methods were called correctly
        mock_data_cache.should_send_alert_for_transition.assert_called_once_with("Red")
        mock_data_cache.record_alert_sent.assert_not_called()  # Should NOT record alert sent
        mock_data_cache.update_risk_level.assert_called_once_with("Red")

    @patch('cache_refresh.get_active_subscribers')
    @patch('cache_refresh.send_orange_to_red_alert')
    @patch('cache_refresh.calculate_fire_risk')
    @patch('cache_refresh.get_synoptic_data')
    @patch('cache_refresh.data_cache')
    def test_midnight_transition(self, mock_data_cache, mock_get_synoptic_data,
                               mock_calculate_risk, mock_send_alert,
                               mock_get_subscribers):
        """Test that an alert is sent for a transition at exactly midnight (new day)."""
        # Set up required mock attributes for testing midnight transition
        current_time = datetime.now(TIMEZONE).replace(hour=0, minute=0, second=1)  # 00:00:01
        yesterday = current_time - timedelta(days=1)
        yesterday_evening = yesterday.replace(hour=23, minute=59, second=59)  # 23:59:59 yesterday
        
        mock_data_cache.update_in_progress = False
        mock_data_cache.previous_risk_level = "Orange"
        mock_data_cache.risk_level_timestamp = current_time  # Just after midnight
        mock_data_cache.last_alerted_timestamp = yesterday_evening  # Just before midnight
        mock_data_cache.max_retries = 5
        mock_data_cache.retry_delay = 0
        mock_data_cache.update_timeout = 15
        mock_data_cache.refresh_task_active = False
        mock_data_cache.using_cached_data = False
        mock_data_cache.cached_fields = {"temperature": False, "humidity": False, "wind_speed": False, "soil_moisture": False}
        
        # Mock the methods
        mock_data_cache.reset_update_event = MagicMock()
        mock_data_cache.update_cache = MagicMock()
        # Should return True because it's a new day
        mock_data_cache.should_send_alert_for_transition = MagicMock(return_value=True)
        mock_data_cache.record_alert_sent = MagicMock()
        mock_data_cache.update_risk_level = MagicMock()
        mock_data_cache.ensure_complete_weather_data.return_value = {
            "air_temp": 32,
            "relative_humidity": 12,
            "wind_speed": 25,
            "wind_gust": 35,
            "soil_moisture_15cm": 8
        }
        
        # Mock API data
        mock_get_synoptic_data.return_value = {"data": "sample"}
        
        # Mock calculating risk level to Red
        mock_calculate_risk.return_value = ("Red", "High temperature and low humidity")
        
        # Mock subscribers list
        mock_get_subscribers.return_value = {"subscribers": ["test@example.com"]}
        
        # Mock send_alert to return a message ID
        mock_send_alert.return_value = "test-message-id"
        
        # Set up the async function to be called synchronously
        async def run_refresh():
            return await refresh_data_cache()
            
        # Run the async function in an event loop
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(run_refresh())
        finally:
            loop.close()
        
        # Verify the results
        self.assertTrue(result)  # Refresh should be successful
        mock_get_subscribers.assert_called_once()  # Should get subscribers for alert
        mock_send_alert.assert_called_once()  # Should send alert because it's a new day
        
        # Verify our methods were called correctly
        mock_data_cache.should_send_alert_for_transition.assert_called_once_with("Red")
        mock_data_cache.record_alert_sent.assert_called_once()  # Should record alert was sent
        mock_data_cache.update_risk_level.assert_called_once_with("Red")

    def test_date_comparison_logic(self):
        """Test the date comparison logic directly to ensure calendar day is used, not time."""
        # Create a cache instance
        data_cache = DataCache()
        
        # Setup the needed attributes
        current_time = datetime.now(TIMEZONE)
        data_cache.previous_risk_level = "Orange"
        data_cache.risk_level_timestamp = current_time
        
        # Test case 1: Last alert was earlier today
        data_cache.last_alerted_timestamp = current_time - timedelta(hours=3)
        result = data_cache.should_send_alert_for_transition("Red")
        self.assertFalse(result, "Should not send alert if already sent today")
        
        # Test case 2: Last alert was yesterday, same time
        data_cache.last_alerted_timestamp = current_time - timedelta(days=1)
        result = data_cache.should_send_alert_for_transition("Red")
        self.assertTrue(result, "Should send alert if last alert was yesterday")
        
        # Test case 3: Last alert was yesterday, but earlier hour
        data_cache.last_alerted_timestamp = current_time - timedelta(days=1, hours=2)
        result = data_cache.should_send_alert_for_transition("Red")
        self.assertTrue(result, "Should send alert if last alert was yesterday, regardless of time")
        
        # Test case 4: Last alert was yesterday, but later hour
        data_cache.last_alerted_timestamp = current_time - timedelta(days=1) + timedelta(hours=2)
        if data_cache.last_alerted_timestamp.date() != current_time.date():  # Only if dates are different
            result = data_cache.should_send_alert_for_transition("Red")
            self.assertTrue(result, "Should send alert if last alert was on a different date")


if __name__ == '__main__':
    unittest.main()

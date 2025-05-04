import unittest
from unittest.mock import patch, MagicMock
import asyncio
import pytest
from datetime import datetime, timedelta

from cache import DataCache
from cache_refresh import refresh_data_cache
from config import TIMEZONE

class TestRiskLevelPersistence(unittest.TestCase):
    """Test the persistence of risk levels across server restarts."""

    @patch('cache_refresh.get_active_subscribers')
    @patch('cache_refresh.send_orange_to_red_alert')
    @patch('cache_refresh.calculate_fire_risk')
    @patch('cache_refresh.get_synoptic_data')
    @patch('cache_refresh.data_cache')
    def test_risk_level_persistence_during_restart(self, mock_data_cache, mock_get_synoptic_data, 
                                                  mock_calculate_risk, mock_send_alert, 
                                                  mock_get_subscribers):
        """Test that risk level transitions are detected even after a server restart."""
        # Set up initial state - server running with Orange risk level
        current_time = datetime.now(TIMEZONE)
        previous_time = current_time - timedelta(hours=1)

        # Set up required mock attributes
        mock_data_cache.previous_risk_level = "Orange"
        mock_data_cache.risk_level_timestamp = previous_time
        mock_data_cache.last_alerted_timestamp = None
        mock_data_cache.update_in_progress = False
        mock_data_cache.max_retries = 5
        mock_data_cache.retry_delay = 0
        mock_data_cache.update_timeout = 15
        mock_data_cache.refresh_task_active = False
        mock_data_cache.using_cached_data = False
        
        # Mock the methods
        mock_data_cache.reset_update_event = MagicMock()
        mock_data_cache.update_cache = MagicMock()
        mock_data_cache.cached_fields = {"temperature": False, "humidity": False, "wind_speed": False, "soil_moisture": False}
        mock_data_cache.ensure_complete_weather_data.return_value = {
            "air_temp": 32,
            "relative_humidity": 12,
            "wind_speed": 25,
            "wind_gust": 35,
            "soil_moisture_15cm": 8
        }
        
        # Mock get_synoptic_data to return sample weather data
        mock_get_synoptic_data.return_value = {"data": "sample"}
        
        # Mock calculate_fire_risk to return "Red" risk level
        mock_calculate_risk.return_value = ("Red", "High temperature and low humidity")
        
        # Mock should_send_alert_for_transition to test our persistence logic
        mock_data_cache.should_send_alert_for_transition.return_value = True
        
        # Mock subscribers list
        mock_get_subscribers.return_value = {"subscribers": ["test@example.com"]}
        
        # Mock send_orange_to_red_alert to return a message ID
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
        
        # Verify our persistence logic was called to check for missed transitions
        mock_data_cache.should_send_alert_for_transition.assert_called_once_with("Red")
        
        # Verify alert was sent
        mock_send_alert.assert_called_once()
        mock_data_cache.record_alert_sent.assert_called_once()
        
        # Verify risk level was updated
        mock_data_cache.update_risk_level.assert_called_once_with("Red")
        
    @patch('cache_refresh.get_active_subscribers')
    @patch('cache_refresh.send_orange_to_red_alert')
    @patch('cache_refresh.calculate_fire_risk')
    @patch('cache_refresh.get_synoptic_data')
    @patch('cache_refresh.data_cache')
    def test_no_duplicate_alerts_after_restart(self, mock_data_cache, mock_get_synoptic_data, 
                                              mock_calculate_risk, mock_send_alert, 
                                              mock_get_subscribers):
        """Test that alerts aren't sent twice for the same transition after a restart."""
        # Set up initial state - server restarting after already having sent an alert
        current_time = datetime.now(TIMEZONE)
        previous_time = current_time - timedelta(hours=1)
        alert_time = current_time - timedelta(minutes=30)  # Alert was sent 30 minutes ago

        # Set up required mock attributes
        mock_data_cache.previous_risk_level = "Orange"
        mock_data_cache.risk_level_timestamp = previous_time
        mock_data_cache.last_alerted_timestamp = alert_time  # Alert was already sent
        mock_data_cache.update_in_progress = False
        mock_data_cache.max_retries = 5
        mock_data_cache.retry_delay = 0
        mock_data_cache.update_timeout = 15
        mock_data_cache.refresh_task_active = False
        mock_data_cache.using_cached_data = False
        
        # Mock the methods
        mock_data_cache.reset_update_event = MagicMock()
        mock_data_cache.update_cache = MagicMock()
        mock_data_cache.cached_fields = {"temperature": False, "humidity": False, "wind_speed": False, "soil_moisture": False}
        mock_data_cache.ensure_complete_weather_data.return_value = {
            "air_temp": 32,
            "relative_humidity": 12,
            "wind_speed": 25,
            "wind_gust": 35,
            "soil_moisture_15cm": 8
        }
        
        # Mock get_synoptic_data to return sample weather data
        mock_get_synoptic_data.return_value = {"data": "sample"}
        
        # Mock calculate_fire_risk to return "Red" risk level
        mock_calculate_risk.return_value = ("Red", "High temperature and low humidity")
        
        # Mock should_send_alert_for_transition to test our persistence logic - should return False
        mock_data_cache.should_send_alert_for_transition.return_value = False
        
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
        
        # Verify our persistence logic was called
        mock_data_cache.should_send_alert_for_transition.assert_called_once_with("Red")
        
        # Verify no alert was sent (since we already alerted)
        mock_send_alert.assert_not_called()
        mock_data_cache.record_alert_sent.assert_not_called()
        
        # Verify risk level was still updated
        mock_data_cache.update_risk_level.assert_called_once_with("Red")

    def test_data_cache_should_send_alert_for_transition(self):
        """Test the should_send_alert_for_transition method of DataCache directly."""
        # Create a real DataCache instance (not a mock)
        cache = DataCache()
        
        # Test case 1: Current risk is not Red
        cache.previous_risk_level = "Orange"
        self.assertFalse(cache.should_send_alert_for_transition("Orange"))
        
        # Test case 2: Previous risk is not Orange
        cache.previous_risk_level = "Red"
        self.assertFalse(cache.should_send_alert_for_transition("Red"))
        
        # Test case 3: First time detecting risk (no timestamp)
        cache.previous_risk_level = "Orange"
        cache.risk_level_timestamp = None
        cache.last_alerted_timestamp = None
        self.assertTrue(cache.should_send_alert_for_transition("Red"))
        
        # Test case 4: Already alerted for this transition
        current_time = datetime.now(TIMEZONE)
        cache.previous_risk_level = "Orange"
        cache.risk_level_timestamp = current_time - timedelta(hours=1)
        cache.last_alerted_timestamp = current_time - timedelta(minutes=30)
        self.assertFalse(cache.should_send_alert_for_transition("Red"))
        
        # Test case 5: New transition after last alert
        cache.previous_risk_level = "Orange"
        cache.risk_level_timestamp = current_time - timedelta(minutes=10)  # Risk changed 10 minutes ago
        cache.last_alerted_timestamp = current_time - timedelta(hours=1)   # Last alert was 1 hour ago
        self.assertTrue(cache.should_send_alert_for_transition("Red"))
    
    def test_update_risk_level(self):
        """Test the update_risk_level method of DataCache."""
        # Use a mock to avoid disk operations
        with patch('cache.DataCache._save_cache_to_disk') as mock_save:
            cache = DataCache()
            
            # Initial state
            cache.previous_risk_level = "Orange"
            cache.risk_level_timestamp = None
            
            # Test updating to a different risk level
            cache.update_risk_level("Red")
            
            # Verify timestamp was updated and save was called
            self.assertEqual(cache.previous_risk_level, "Red")
            self.assertIsNotNone(cache.risk_level_timestamp)
            mock_save.assert_called_once()
            
            # Reset mock
            mock_save.reset_mock()
            
            # Test updating to the same risk level (should not change timestamp)
            old_timestamp = cache.risk_level_timestamp
            cache.update_risk_level("Red")
            
            # Verify timestamp was not updated and save was not called
            self.assertEqual(cache.risk_level_timestamp, old_timestamp)
            mock_save.assert_not_called()
            
    def test_record_alert_sent(self):
        """Test the record_alert_sent method of DataCache."""
        # Use a mock to avoid disk operations
        with patch('cache.DataCache._save_cache_to_disk') as mock_save:
            cache = DataCache()
            
            # Initial state
            cache.last_alerted_timestamp = None
            
            # Record an alert
            cache.record_alert_sent()
            
            # Verify timestamp was updated and save was called
            self.assertIsNotNone(cache.last_alerted_timestamp)
            mock_save.assert_called_once()

if __name__ == '__main__':
    unittest.main()

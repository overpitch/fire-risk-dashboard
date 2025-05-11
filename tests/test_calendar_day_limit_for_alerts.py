import unittest
from unittest.mock import patch, MagicMock
import asyncio
from datetime import datetime, timedelta

from cache import DataCache
from config import TIMEZONE

class TestCalendarDayLimitForAlerts(unittest.TestCase):
    """Test that Orange to Red transition alerts are limited to once per calendar day."""

    def setUp(self):
        """Set up the test case with a mock DataCache instance."""
        self.data_cache = DataCache()
        self.data_cache.previous_risk_level = "Orange"
        # Set up a timestamp for risk level update
        self.data_cache.risk_level_timestamp = datetime.now(TIMEZONE) - timedelta(hours=1)

    def test_first_alert_is_sent(self):
        """Test that the first Orange to Red transition of the day should send an alert."""
        # No previous alert
        self.data_cache.last_alerted_timestamp = None
        
        # Should send alert for first transition
        result = self.data_cache.should_send_alert_for_transition("Red")
        self.assertTrue(result, "First Orange to Red transition should send an alert")

    def test_same_day_alert_is_not_sent(self):
        """Test that a second alert on the same calendar day is not sent."""
        # Previous alert was earlier today
        current_time = datetime.now(TIMEZONE)
        self.data_cache.last_alerted_timestamp = current_time - timedelta(hours=2)
        
        # Risk level changed after the last alert
        self.data_cache.risk_level_timestamp = current_time - timedelta(hours=1)
        
        # Should not send another alert on the same day
        result = self.data_cache.should_send_alert_for_transition("Red")
        self.assertFalse(result, "Second Orange to Red transition on the same day should not send an alert")

    def test_different_day_alert_is_sent(self):
        """Test that an alert is sent if the transition happens on a different calendar day."""
        # Previous alert was yesterday
        current_time = datetime.now(TIMEZONE)
        self.data_cache.last_alerted_timestamp = current_time - timedelta(days=1)
        
        # Risk level changed after the last alert
        self.data_cache.risk_level_timestamp = current_time - timedelta(hours=1)
        
        # Should send an alert on a new day
        result = self.data_cache.should_send_alert_for_transition("Red")
        self.assertTrue(result, "Orange to Red transition on a new calendar day should send an alert")

    def test_different_risk_levels_no_alert(self):
        """Test that no alert is sent for risk levels other than Orange to Red transition."""
        test_cases = [
            ("Green", False),   # Green should never trigger an Orange to Red alert
            ("Orange", False),  # Orange risk level should not trigger an alert
            ("Yellow", False)   # Any other risk level should not trigger
        ]
        
        for risk_level, expected_result in test_cases:
            result = self.data_cache.should_send_alert_for_transition(risk_level)
            self.assertEqual(result, expected_result, f"Risk level {risk_level} should return {expected_result}")

    def test_previous_level_not_orange_no_alert(self):
        """Test that no alert is sent if the previous risk level was not Orange."""
        # Set previous risk level to something other than Orange
        self.data_cache.previous_risk_level = "Green"
        
        # Should not send an alert even if current risk is Red
        result = self.data_cache.should_send_alert_for_transition("Red")
        self.assertFalse(result, "No alert should be sent if previous risk was not Orange")

if __name__ == '__main__':
    unittest.main()

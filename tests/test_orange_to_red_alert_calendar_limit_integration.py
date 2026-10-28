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


# --- Full refresh cycles with a real DataCache and a controlled clock ---

@pytest.mark.asyncio
async def test_multiple_transitions_same_day(alert_env):
    """Orange->Red alerts once; Red->Orange->Red again later the same day does not alert again."""
    day = datetime(2026, 8, 15, 9, 0, tzinfo=TIMEZONE)
    alert_env.set_time(day)
    cache = alert_env.start_server()
    cache.update_risk_level("Orange")

    alert_env.set_time(day + timedelta(hours=1))
    (await alert_env.refresh_with_risk(cache, "Red")).assert_called_once()

    alert_env.set_time(day + timedelta(hours=3))
    (await alert_env.refresh_with_risk(cache, "Orange")).assert_not_called()

    alert_env.set_time(day + timedelta(hours=6))
    (await alert_env.refresh_with_risk(cache, "Red")).assert_not_called()


@pytest.mark.asyncio
async def test_midnight_transition(alert_env):
    """An alert just before midnight doesn't block a new Orange->Red transition just after it."""
    evening = datetime(2026, 8, 15, 23, 59, 0, tzinfo=TIMEZONE)
    alert_env.set_time(evening - timedelta(hours=1))
    cache = alert_env.start_server()
    cache.update_risk_level("Orange")

    alert_env.set_time(evening)
    (await alert_env.refresh_with_risk(cache, "Red")).assert_called_once()

    alert_env.set_time(evening + timedelta(seconds=30))
    (await alert_env.refresh_with_risk(cache, "Orange")).assert_not_called()

    alert_env.set_time(evening + timedelta(minutes=2))  # 00:01 the next day
    (await alert_env.refresh_with_risk(cache, "Red")).assert_called_once()


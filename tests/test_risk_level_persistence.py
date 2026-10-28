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
        
        # Test case 5: New transition, last alert was on an earlier day
        cache.previous_risk_level = "Orange"
        cache.risk_level_timestamp = current_time - timedelta(minutes=10)  # Risk changed 10 minutes ago
        cache.last_alerted_timestamp = current_time - timedelta(days=1)    # Last alert was yesterday
        self.assertTrue(cache.should_send_alert_for_transition("Red"))

        # Test case 6: New transition, but an alert already went out today (once-per-calendar-day limit)
        cache.last_alerted_timestamp = cache.risk_level_timestamp - timedelta(seconds=1)
        same_day = cache.last_alerted_timestamp.date() == current_time.date()
        self.assertEqual(cache.should_send_alert_for_transition("Red"), not same_day)
    
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


# --- Restart behaviour with a real DataCache saved to a temporary folder ---

@pytest.mark.asyncio
async def test_risk_level_persistence_during_restart(alert_env):
    """An Orange level saved before a restart is remembered, so a move to Red after it still alerts."""
    before_restart = alert_env.start_server()
    before_restart.update_risk_level("Orange")

    after_restart = alert_env.start_server()
    assert after_restart.previous_risk_level == "Orange"

    (await alert_env.refresh_with_risk(after_restart, "Red")).assert_called_once()
    assert after_restart.previous_risk_level == "Red"


@pytest.mark.asyncio
async def test_no_duplicate_alerts_after_restart(alert_env):
    """After an alert has gone out, a restart while still Red must not send it again."""
    first_run = alert_env.start_server()
    first_run.update_risk_level("Orange")
    (await alert_env.refresh_with_risk(first_run, "Red")).assert_called_once()

    after_restart = alert_env.start_server()
    assert after_restart.last_alerted_timestamp is not None
    (await alert_env.refresh_with_risk(after_restart, "Red")).assert_not_called()


@pytest.mark.asyncio
async def test_alert_state_saved_in_configured_cache_dir(alert_env, tmp_path):
    """CACHE_DIR decides where the risk level and alert time are saved (the persistent disk on Render)."""
    disk = tmp_path / "persistent-disk"
    with patch('cache.CACHE_DIR', str(disk)):
        cache = alert_env.start_server()
        cache.update_risk_level("Orange")
        assert (disk / "weather_cache.json").exists()
        assert not (tmp_path / "data" / "weather_cache.json").exists()

        assert alert_env.start_server().previous_risk_level == "Orange"

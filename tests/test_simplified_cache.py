import pytest
from datetime import datetime, timedelta
import asyncio
from typing import Dict, Any

from simplified_cache import DataCache
from config import TIMEZONE

# Mock data for testing
MOCK_SYNOPTIC_DATA = {"STATION": [{"STID": "TEST1", "OBSERVATIONS": {"air_temp_value_1": {"value": 20.0}}}]}
MOCK_WUNDERGROUND_DATA = {"KCASIERR68": {"observations": [{"imperial": {"windGust": 7.0}}]}}
MOCK_FIRE_RISK_DATA = {
    "risk": "Moderate",
    "explanation": "Test explanation",
    "weather": {
        "air_temp": 20.0,
        "relative_humidity": 45.0,
        "wind_speed": 7.0,  # This is the critical value we need to track
        "soil_moisture_15cm": 25.0,
        "wind_gust": 10.0
    }
}

class TestSimplifiedCache:
    """Tests for the simplified snapshot-based caching system"""
    
    def setup_method(self):
        """Set up a fresh cache instance for each test"""
        self.cache = DataCache()
        # Override cache file path to avoid conflicts with real cache
        self.cache.cache_file = "data/test_weather_cache.json"
        # Create a test directory if it doesn't exist
        import os
        os.makedirs("data", exist_ok=True)
        
        # Reset internal state and reinitialize with default values
        current_time = datetime.now(TIMEZONE)
        default_snapshot = {
            "synoptic_data": None,
            "wunderground_data": None,
            "fire_risk_data": {
                "risk": "Unknown",
                "explanation": "Test data",
                "weather": {
                    "air_temp": self.cache.DEFAULT_VALUES["temperature"],
                    "relative_humidity": self.cache.DEFAULT_VALUES["humidity"],
                    "wind_speed": self.cache.DEFAULT_VALUES["wind_speed"],
                    "soil_moisture_15cm": self.cache.DEFAULT_VALUES["soil_moisture"],
                    "wind_gust": self.cache.DEFAULT_VALUES["wind_gust"],
                }
            },
            "timestamp": current_time,
            "is_default": True
        }
        
        self.cache.snapshots = [default_snapshot]
        self.cache.current_snapshot = default_snapshot
        self.cache.last_updated = current_time
        self.cache.using_cached_data = True
    
    def test_initial_state(self):
        """Test that the cache initializes with default values"""
        # A fresh cache should have default values
        assert self.cache.using_cached_data == True
        assert self.cache.current_snapshot is not None
        assert self.cache.current_snapshot.get("is_default") == True
    
    def test_update_cache(self):
        """Test that update_cache creates a proper snapshot"""
        # Update the cache with mock data
        self.cache.update_cache(MOCK_SYNOPTIC_DATA, MOCK_WUNDERGROUND_DATA, MOCK_FIRE_RISK_DATA)
        
        # Verify the snapshot was created correctly
        assert self.cache.using_cached_data == False
        # We now have 2 snapshots (the default one and the new one)
        assert len(self.cache.snapshots) == 2
        assert self.cache.current_snapshot is not None
        assert self.cache.current_snapshot.get("synoptic_data") == MOCK_SYNOPTIC_DATA
        assert self.cache.current_snapshot.get("wunderground_data") == MOCK_WUNDERGROUND_DATA
        assert self.cache.current_snapshot.get("fire_risk_data") == MOCK_FIRE_RISK_DATA
        
        # Verify the last_updated timestamp was set
        assert self.cache.last_updated is not None
        
        # Most importantly, check that the wind speed is correct
        fire_risk_data = self.cache.current_snapshot.get("fire_risk_data")
        assert fire_risk_data["weather"]["wind_speed"] == 7.0
    
    def test_is_stale(self):
        """Test the is_stale method correctly identifies old data"""
        # Set up a snapshot from an hour ago
        current_time = datetime.now(TIMEZONE)
        old_time = current_time - timedelta(minutes=61)
        
        self.cache.update_cache(MOCK_SYNOPTIC_DATA, MOCK_WUNDERGROUND_DATA, MOCK_FIRE_RISK_DATA)
        
        # Manually set the last_updated timestamp to simulate old data
        self.cache.last_updated = old_time
        self.cache.current_snapshot["timestamp"] = old_time
        
        # Check if data is identified as stale
        assert self.cache.is_stale(max_age_minutes=60) == True
        
        # Data should not be stale if we use a higher threshold
        assert self.cache.is_stale(max_age_minutes=120) == False
    
    def test_mark_as_stale(self):
        """Test marking data as stale"""
        # Start with fresh data
        self.cache.update_cache(MOCK_SYNOPTIC_DATA, MOCK_WUNDERGROUND_DATA, MOCK_FIRE_RISK_DATA)
        assert self.cache.using_cached_data == False
        
        # Mark it as stale
        self.cache.mark_as_stale()
        
        # Should now be marked as cached
        assert self.cache.using_cached_data == True
    
    def test_get_latest_data(self):
        """Test retrieving the latest data"""
        # Update the cache with mock data
        self.cache.update_cache(MOCK_SYNOPTIC_DATA, MOCK_WUNDERGROUND_DATA, MOCK_FIRE_RISK_DATA)
        
        # Get the latest data
        latest_data = self.cache.get_latest_data()
        
        # Verify it's the correct data
        assert latest_data.get("fire_risk_data") == MOCK_FIRE_RISK_DATA
        
        # Check the wind speed
        assert latest_data["fire_risk_data"]["weather"]["wind_speed"] == 7.0
    
    def test_historical_snapshots(self):
        """Test that historical snapshots are maintained"""
        # Create several snapshots with different data
        for i in range(5):
            mock_fire_risk = MOCK_FIRE_RISK_DATA.copy()
            mock_fire_risk["weather"] = mock_fire_risk["weather"].copy()
            mock_fire_risk["weather"]["wind_speed"] = float(i + 3)  # 3, 4, 5, 6, 7
            
            self.cache.update_cache(MOCK_SYNOPTIC_DATA, MOCK_WUNDERGROUND_DATA, mock_fire_risk)
        
        # Should have 6 snapshots (1 default + 5 new ones)
        assert len(self.cache.snapshots) == 6
        
        # The current snapshot should have wind_speed == 7.0
        assert self.cache.current_snapshot["fire_risk_data"]["weather"]["wind_speed"] == 7.0
        
        # The default snapshot is at index 0, the snapshots we created are at indices 1-5
        # The first snapshot we created (with wind_speed 3.0) should be at index 1
        assert self.cache.snapshots[1]["fire_risk_data"]["weather"]["wind_speed"] == 3.0

# Run with: pytest -xvs tests/test_simplified_cache.py

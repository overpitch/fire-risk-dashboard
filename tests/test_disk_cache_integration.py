import pytest
import os
import shutil
import json
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi.testclient import TestClient
from main import app
from cache import DataCache, data_cache
from config import TIMEZONE

client = TestClient(app)

@pytest.fixture
def setup_disk_cache():
    """Setup a test disk cache and clean up after."""
    # Create test directory
    cache_dir = Path("data")
    cache_file = cache_dir / "weather_cache.json"
    
    # Remember original cache file if it exists
    original_exists = cache_file.exists()
    original_data = None
    if original_exists:
        with open(cache_file, 'r') as f:
            original_data = f.read()
    
    # Create test data
    test_time = datetime.now(TIMEZONE)
    test_data = {
        "last_valid_data": {
            "fields": {
                "temperature": {"value": 22.5, "timestamp": test_time.isoformat()},
                "humidity": {"value": 55.0, "timestamp": test_time.isoformat()},
                "wind_speed": {"value": 7.5, "timestamp": test_time.isoformat()},
                "soil_moisture": {"value": 30.0, "timestamp": test_time.isoformat()},
                "wind_gust": {
                    "value": 12.0, 
                    "timestamp": test_time.isoformat(),
                    "stations": {}
                }
            },
            "synoptic_data": None,
            "wunderground_data": None,
            "fire_risk_data": {
                "risk": "Orange",
                "explanation": "Low to Moderate fire risk."
            },
            "timestamp": test_time.isoformat()
        },
        "last_updated": test_time.isoformat()
    }
    
    # Ensure directory exists
    os.makedirs(cache_dir, exist_ok=True)
    
    # Write test data
    with open(cache_file, 'w') as f:
        json.dump(test_data, f)
    
    yield test_data
    
    # Restore original file or remove if it didn't exist
    if original_exists and original_data:
        with open(cache_file, 'w') as f:
            f.write(original_data)
    else:
        if cache_file.exists():
            os.remove(cache_file)


@pytest.mark.asyncio
async def test_disk_cache_loading_on_startup(setup_disk_cache):
    """Test that the disk cache is loaded on startup."""
    # Create a new cache instance (simulating startup)
    cache = DataCache()
    
    # Check that the values match what we put in the disk cache
    assert cache.last_valid_data["fields"]["temperature"]["value"] == 22.5
    assert cache.last_valid_data["fields"]["humidity"]["value"] == 55.0
    assert cache.last_valid_data["fields"]["wind_speed"]["value"] == 7.5
    assert cache.last_valid_data["fields"]["soil_moisture"]["value"] == 30.0
    assert cache.last_valid_data["fields"]["wind_gust"]["value"] == 12.0


@pytest.mark.asyncio
async def test_cache_persistence(setup_disk_cache):
    """Test that the cache persists changes to disk."""
    # Create a new cache instance with the initial disk data
    cache = DataCache()
    
    # Modify some values
    new_temp = 25.0
    cache.last_valid_data["fields"]["temperature"]["value"] = new_temp
    
    # Force save to disk
    cache._save_cache_to_disk()
    
    # Create another instance to verify changes were persisted
    new_cache = DataCache()
    assert new_cache.last_valid_data["fields"]["temperature"]["value"] == new_temp


@pytest.mark.asyncio
async def test_four_level_fallback_with_disk(setup_disk_cache):
    """Test the complete 4-level fallback system."""
    # Create a new cache instance
    cache = DataCache()
    
    # 1. Direct API data (highest priority)
    direct_temp = 30.0
    cache.fire_risk_data = {
        "weather": {
            "air_temp": direct_temp
        }
    }
    
    # Should use direct API value
    assert cache.get_field_value("temperature") == direct_temp
    
    # 2. In-memory cached data (second priority)
    in_memory_temp = 28.0
    cache.fire_risk_data = {"weather": {}}  # Remove direct value
    cache.last_valid_data["fields"]["temperature"]["value"] = in_memory_temp
    
    # Should use in-memory value
    assert cache.get_field_value("temperature") == in_memory_temp
    
    # 3. Disk-cached data (third priority)
    # This is already tested in test_disk_cache_loading_on_startup
    
    # 4. Default values (lowest priority)
    cache.last_valid_data["fields"]["temperature"]["value"] = None
    
    # Should use default value
    assert cache.get_field_value("temperature") == DataCache.DEFAULT_VALUES["temperature"]


@pytest.mark.asyncio
async def test_ensuring_complete_data_with_disk_cache(setup_disk_cache):
    """Test that ensure_complete_weather_data fills missing values from disk cache."""
    # Create a new cache instance with disk-loaded data
    cache = DataCache()
    
    # Create incomplete weather data
    incomplete_data = {
        "air_temp": None,
        # Missing humidity
        "wind_speed": 15.0,
        # Missing soil_moisture_15cm
        "wind_gust": None
    }
    
    # Complete the data
    complete_data = cache.ensure_complete_weather_data(incomplete_data)
    
    # Verify values were filled from disk cache
    assert complete_data["air_temp"] == 22.5  # From disk cache
    assert complete_data["relative_humidity"] == 55.0  # From disk cache
    assert complete_data["wind_speed"] == 15.0  # From direct data
    assert complete_data["soil_moisture_15cm"] == 30.0  # From disk cache
    assert complete_data["wind_gust"] == 12.0  # From disk cache

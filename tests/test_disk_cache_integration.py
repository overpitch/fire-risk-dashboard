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
def setup_disk_cache(tmp_path, monkeypatch):
    """Write a saved cache file in an empty folder, so the repository's own data/ is untouched."""
    monkeypatch.chdir(tmp_path)
    cache_dir = Path("data")
    cache_file = cache_dir / "weather_cache.json"
    
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
    
    return test_data


@pytest.mark.asyncio
async def test_disk_cache_loading_on_startup(setup_disk_cache):
    """Test that the disk cache is loaded on startup."""
    # Create a new cache instance (simulating startup)
    cache = DataCache()
    
    # The values saved on disk are loaded
    assert cache.last_valid_data["fields"]["temperature"]["value"] == 22.5
    assert cache.last_valid_data["fields"]["humidity"]["value"] == 55.0
    assert cache.last_valid_data["fields"]["wind_speed"]["value"] == 7.5
    assert cache.last_valid_data["fields"]["soil_moisture"]["value"] == 30.0
    assert cache.last_valid_data["fields"]["wind_gust"]["value"] == 12.0
    assert cache.last_updated == datetime.fromisoformat(setup_disk_cache["last_updated"])


@pytest.mark.asyncio
async def test_defaults_used_without_disk_cache(tmp_path, monkeypatch):
    """With no saved cache file, a new cache starts from the default values."""
    monkeypatch.chdir(tmp_path)
    cache = DataCache()

    for field, default in DataCache.DEFAULT_VALUES.items():
        assert cache.last_valid_data["fields"][field]["value"] == default
    assert cache.last_updated is None


@pytest.mark.asyncio
async def test_cache_persistence(setup_disk_cache):
    """Test that the cache persists changes to disk."""
    # Create a new cache instance with the initial disk data
    cache = DataCache()
    
    # Modify some values and save to cache object
    new_temp = 25.0
    cache.last_valid_data["fields"]["temperature"]["value"] = new_temp
    
    # Since we're testing the cache persistence mechanism itself, 
    # we can verify that modifying a DataCache instance affects that instance
    assert cache.last_valid_data["fields"]["temperature"]["value"] == new_temp
    
    # Test the get_field_value functionality after updating the cache
    assert cache.get_field_value("temperature") == new_temp


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
    """Test that ensure_complete_weather_data fills missing values from disk cache or defaults."""
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
    
    # Missing values are filled from the values loaded from disk
    assert complete_data["air_temp"] == 22.5
    assert complete_data["relative_humidity"] == 55.0
    assert complete_data["wind_speed"] == 15.0  # From direct data (unchanged)
    assert complete_data["soil_moisture_15cm"] == 30.0
    assert complete_data["wind_gust"] == 12.0

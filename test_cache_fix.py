import os
import sys
import json
from datetime import datetime
import pytz

# Add the current directory to path so we can import local modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import TIMEZONE, logger
from cache import DataCache

def test_cache_state_preservation():
    """Test that cached fields state is properly preserved during updates."""
    print("\n🧪 Testing cache state preservation...")
    
    # Create a new cache instance
    cache = DataCache()
    
    # Create some test data
    synoptic_data = {"test": "synoptic_data"}
    
    # Create test fire risk data with missing wind data to simulate API issue
    fire_risk_data = {
        "weather": {
            "air_temp": 25.0,
            "relative_humidity": 30.0,
            "wind_speed": None,  # Missing wind speed
            "soil_moisture_15cm": 10.0,
            "wind_gust": None,   # Missing wind gust
        },
        "risk_level": "Orange"
    }
    
    # Initial update - some fields missing
    print("\n⬇️ Initial update with missing wind data")
    cache.update_cache(synoptic_data, fire_risk_data)
    
    # Check current cache state
    print(f"Using cached data: {cache.using_cached_data}")
    print(f"Cached fields: {', '.join([f for f, v in cache.cached_fields.items() if v])}")
    
    # Create new data with all fields present
    complete_fire_risk_data = {
        "weather": {
            "air_temp": 25.0,
            "relative_humidity": 30.0,
            "wind_speed": 15.0,  # Wind speed present
            "soil_moisture_15cm": 10.0,
            "wind_gust": 20.0,   # Wind gust present
        },
        "risk_level": "Orange"
    }
    
    # Second update - all fields present
    print("\n⬇️ Second update with complete data")
    cache.update_cache(synoptic_data, complete_fire_risk_data)
    
    # Check cache state again
    print(f"Using cached data: {cache.using_cached_data}")
    print(f"Cached fields: {', '.join([f for f, v in cache.cached_fields.items() if v])}")
    
    # Now simulate a situation where we're back to missing data
    missing_data_again = {
        "weather": {
            "air_temp": 26.0,
            "relative_humidity": 31.0,
            "wind_speed": None,  # Missing wind speed again
            "soil_moisture_15cm": 11.0,
            "wind_gust": None,   # Missing wind gust again
        },
        "risk_level": "Orange"
    }
    
    # Third update - back to missing data
    print("\n⬇️ Third update with missing data again")
    cache.update_cache(synoptic_data, missing_data_again)
    
    # Check final cache state
    print(f"Using cached data: {cache.using_cached_data}")
    print(f"Cached fields: {', '.join([f for f, v in cache.cached_fields.items() if v])}")
    
    # Test getting values with fallback
    wind_speed = cache.get_field_value("wind_speed")
    wind_gust = cache.get_field_value("wind_gust")
    
    print(f"\n📊 Retrieved wind_speed: {wind_speed} (using cached: {cache.cached_fields['wind_speed']})")
    print(f"📊 Retrieved wind_gust: {wind_gust} (using cached: {cache.cached_fields['wind_gust']})")
    
    print("\n✅ Test completed")

if __name__ == "__main__":
    test_cache_state_preservation()

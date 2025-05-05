import os
import sys
import json
from datetime import datetime, timedelta
import pytz

# Add the current directory to path so we can import local modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import TIMEZONE, logger, WIND_STATION_ID
from data_processing import process_synoptic_data, combine_weather_data
from api_clients import get_synoptic_data
from fire_risk_logic import calculate_fire_risk
from cache import data_cache  # Use the existing cache instance

def verify_wind_data_fix():
    """Verify that wind data is working correctly with the fixed cache system."""
    print("\n🔍 Verifying wind data with fixed cache system...")
    
    # Step 1: Get the current data from the Synoptic API
    print("\n📡 Fetching data from Synoptic API...")
    synoptic_data = get_synoptic_data()
    
    if synoptic_data is None:
        print("❌ Failed to get data from Synoptic API - using cached data")
    else:
        air_temp, relative_humidity, wind_speed, wind_gust, soil_moisture, found_stations, missing_stations = process_synoptic_data(synoptic_data)
        
        print(f"\n🌡️ Temperature: {air_temp}°C ({air_temp * 9/5 + 32:.1f}°F)")
        print(f"💧 Humidity: {relative_humidity}%")
        print(f"💨 Wind Speed: {wind_speed} m/s ({wind_speed * 2.237:.1f} mph)")
        print(f"🌬️ Wind Gust: {wind_gust} m/s ({wind_gust * 2.237:.1f} mph)")
        print(f"🌱 Soil Moisture: {soil_moisture}%")
        
        # Print which stations were found vs missing
        print(f"\n📍 Found stations: {', '.join(found_stations)}")
        print(f"❓ Missing stations: {', '.join(missing_stations)}")
    
    # Step 2: Get the combined data using the fixed cache
    combined_data = combine_weather_data(synoptic_data, data_cache.last_valid_data)
    
    # Step 3: Calculate fire risk
    fire_risk_data = calculate_fire_risk(combined_data)
    
    # Step 4: Update the cache with the fire risk data
    data_cache.update_cache(synoptic_data, {"weather": combined_data, "risk": fire_risk_data})
    
    # Step 5: Verify the cache state
    print("\n🔄 Cache state after update:")
    print(f"Using cached data: {data_cache.using_cached_data}")
    cached_fields = [f for f, v in data_cache.cached_fields.items() if v]
    print(f"Cached fields: {', '.join(cached_fields) if cached_fields else 'None'}")
    
    # Step 6: Show current values from cache
    temp = data_cache.get_field_value("temperature")
    humidity = data_cache.get_field_value("humidity") 
    wind_speed = data_cache.get_field_value("wind_speed")
    wind_gust = data_cache.get_field_value("wind_gust")
    soil_moisture = data_cache.get_field_value("soil_moisture")
    
    print("\n📊 Current Data (with fallback to cache if needed):")
    print(f"🌡️ Temperature: {temp:.1f}°C ({temp * 9/5 + 32:.1f}°F) [Cached: {data_cache.cached_fields['temperature']}]")
    print(f"💧 Humidity: {humidity:.1f}% [Cached: {data_cache.cached_fields['humidity']}]")
    print(f"💨 Wind Speed: {wind_speed:.1f} mph [Cached: {data_cache.cached_fields['wind_speed']}]")
    print(f"🌬️ Wind Gust: {wind_gust:.1f} mph [Cached: {data_cache.cached_fields['wind_gust']}]")
    print(f"🌱 Soil Moisture: {soil_moisture:.1f}% [Cached: {data_cache.cached_fields['soil_moisture']}]")
    
    # Step 7: Test with missing wind data to ensure proper fallback
    print("\n🧪 Testing with missing wind data...")
    # Create a modified version of the data with wind fields set to None
    modified_synoptic_data = None
    if synoptic_data and "STATION" in synoptic_data:
        modified_synoptic_data = synoptic_data.copy()
        for station in modified_synoptic_data["STATION"]:
            if station.get("STID") == WIND_STATION_ID:
                if "OBSERVATIONS" in station:
                    if "wind_speed_value_1" in station["OBSERVATIONS"]:
                        station["OBSERVATIONS"]["wind_speed_value_1"]["value"] = None
                    if "wind_gust_value_1" in station["OBSERVATIONS"]:
                        station["OBSERVATIONS"]["wind_gust_value_1"]["value"] = None
    
    # Process the modified data
    if modified_synoptic_data:
        print("📋 Processing modified data with missing wind values...")
        modified_combined_data = combine_weather_data(modified_synoptic_data, data_cache.last_valid_data)
        modified_fire_risk_data = calculate_fire_risk(modified_combined_data)
        
        # Update cache with the modified data (missing wind values)
        data_cache.update_cache(modified_synoptic_data, {"weather": modified_combined_data, "risk": modified_fire_risk_data})
        
        # Check cache state after update with missing wind data
        print("\n🔄 Cache state after update with missing wind data:")
        print(f"Using cached data: {data_cache.using_cached_data}")
        cached_fields = [f for f, v in data_cache.cached_fields.items() if v]
        print(f"Cached fields: {', '.join(cached_fields) if cached_fields else 'None'}")
        
        # Check that wind values are coming from cache now
        wind_speed_after = data_cache.get_field_value("wind_speed")
        wind_gust_after = data_cache.get_field_value("wind_gust")
        
        print(f"\n📊 Wind data after update with missing values:")
        print(f"💨 Wind Speed: {wind_speed_after:.1f} mph [Cached: {data_cache.cached_fields['wind_speed']}]")
        print(f"🌬️ Wind Gust: {wind_gust_after:.1f} mph [Cached: {data_cache.cached_fields['wind_gust']}]")
        
        # Verify wind data is correctly preserved from previous valid values
        print(f"\n📈 Wind data preservation check:")
        if wind_speed_after == wind_speed and data_cache.cached_fields['wind_speed']:
            print(f"✅ Wind speed correctly preserved: {wind_speed_after:.1f} mph")
        else:
            print(f"❌ Wind speed not preserved properly. Before: {wind_speed:.1f}, After: {wind_speed_after:.1f}")
            
        if wind_gust_after == wind_gust and data_cache.cached_fields['wind_gust']:
            print(f"✅ Wind gust correctly preserved: {wind_gust_after:.1f} mph")
        else:
            print(f"❌ Wind gust not preserved properly. Before: {wind_gust:.1f}, After: {wind_gust_after:.1f}")
    else:
        print("⚠️ Could not create modified test data - skipping this test")
    
    print("\n✅ Verification completed")

if __name__ == "__main__":
    verify_wind_data_fix()

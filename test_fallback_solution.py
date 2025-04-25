#!/usr/bin/env python
"""
Test script for the Synoptic API fallback solution.

This script tests whether our solution correctly handles 403 Forbidden errors
from the Synoptic API and uses fallback data in development environments.
"""

import os
import json
import logging
import api_clients
from config import SOIL_MOISTURE_STATION_ID, WEATHER_STATION_ID, WIND_STATION_ID

# Set up detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_fallback")

def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f"📋 {title}")
    print("=" * 80)

def test_api_with_fallback():
    """Test the API client with fallback handling."""
    print_section("ENVIRONMENT DETECTION")
    
    # Check if we're in development or production mode
    is_production = os.getenv("RENDER") is not None
    print(f"Running in {'PRODUCTION' if is_production else 'DEVELOPMENT'} mode")
    
    print_section("TOKEN ACQUISITION TEST")
    token = api_clients.get_api_token()
    print(f"Successfully got API token: {token is not None}")
    if token:
        print(f"Token preview: {token[:10]}...")
    
    print_section("WEATHER DATA TEST")
    station_ids = f"{SOIL_MOISTURE_STATION_ID},{WEATHER_STATION_ID},{WIND_STATION_ID}"
    data = api_clients.get_weather_data(station_ids)
    
    is_fallback = data and data.get("SUMMARY", {}).get("FALLBACK_DATA", False)
    print(f"Data retrieved: {data is not None}")
    print(f"Using fallback data: {is_fallback}")
    
    if data:
        stations = data.get("STATION", [])
        print(f"Number of stations: {len(stations)}")
        for station in stations:
            print(f"Station: {station.get('STID')} - {station.get('NAME')}")
            # Print some sensor data as example
            sensors = station.get("SENSOR_VARIABLES", {})
            for sensor_name, sensor_info in sensors.items():
                value = sensor_info.get("value")
                unit = sensor_info.get("unit")
                print(f"  - {sensor_name}: {value} {unit}")
    else:
        print("No data retrieved!")
    
    print_section("SYNOPTIC DATA TEST")
    synoptic_data = api_clients.get_synoptic_data()
    print(f"Synoptic data retrieved: {synoptic_data is not None}")
    print(f"Using fallback data: {synoptic_data and synoptic_data.get('SUMMARY', {}).get('FALLBACK_DATA', False)}")
    
    print_section("DETAILED INFORMATION")
    # Show all SUMMARY information
    if synoptic_data and "SUMMARY" in synoptic_data:
        print("\nSummary Information:")
        for key, value in synoptic_data["SUMMARY"].items():
            print(f"  - {key}: {value}")
    
    # Check if we have cache files
    fallback_path = api_clients.FALLBACK_DATA_PATH
    print(f"\nFallback data path: {fallback_path}")
    print(f"Fallback data exists: {os.path.exists(fallback_path)}")
    
    if os.path.exists(fallback_path):
        size = os.path.getsize(fallback_path)
        modified = os.path.getmtime(fallback_path)
        print(f"Fallback file size: {size} bytes")
        print(f"Last modified: {modified}")

def main():
    """Main function to run the test."""
    try:
        test_api_with_fallback()
    except Exception as e:
        print(f"ERROR: Test failed with exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

#!/usr/bin/env python
import asyncio
import os
import sys
import subprocess
from cache_refresh import refresh_data_cache
from cache import data_cache

async def ensure_fresh_data():
    """Ensure we have fresh data on server startup."""
    print("Ensuring fresh weather data before starting server...")
    
    # Force a complete refresh of the cache
    success = await refresh_data_cache(force=True)
    
    # Verify the wind data is fresh
    if not success:
        print("WARNING: Initial data refresh failed. Server will start with stale data.")
    else:
        print(f"Wind Speed: {data_cache.get_field_value('wind_speed')} m/s")
        print(f"Wind Gust: {data_cache.get_field_value('wind_gust')} m/s")
        
        if data_cache.cached_fields['wind_speed'] or data_cache.cached_fields['wind_gust']:
            print("WARNING: Wind data is still marked as cached after refresh.")
        else:
            print("✅ Wind data successfully refreshed.")

def start_server():
    """Start the FastAPI server using uvicorn."""
    print("\nStarting server with fresh data...")
    # Use the same command that would normally start your server
    # This assumes you're using uvicorn to run the FastAPI app in main.py
    cmd = ["uvicorn", "main:app", "--reload"]
    
    try:
        # Execute the command
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nServer stopped.")
    except Exception as e:
        print(f"Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Run the async function to ensure fresh data
    asyncio.run(ensure_fresh_data())
    
    # Then start the server
    start_server()

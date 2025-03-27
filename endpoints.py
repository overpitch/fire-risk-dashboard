from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse
from typing import Dict, Any
import os
import pathlib
from datetime import datetime

from config import logger, TIMEZONE
from cache import data_cache
from cache_refresh import refresh_data_cache
from data_processing import format_age_string

# Create a router for the main endpoints
router = APIRouter()

@router.get("/fire-risk")
async def fire_risk(background_tasks: BackgroundTasks, wait_for_fresh: bool = False):
    """API endpoint to fetch fire risk status.
    
    Args:
        background_tasks: FastAPI BackgroundTasks for scheduling refreshes
        wait_for_fresh: If True, wait for fresh data instead of returning stale data
    """
    # First-time fetch (cache empty)
    if data_cache.fire_risk_data is None:
        logger.info("Initial data fetch (cache empty)")
        await refresh_data_cache(background_tasks)
        
        # If still no data after refresh, we have a problem
        if data_cache.fire_risk_data is None:
            logger.error("No data available in cache after refresh attempt")
            raise HTTPException(
                status_code=503,
                detail="Weather data service unavailable. Please try again later."
            )
    
    # Check if data is stale
    is_stale = data_cache.is_stale(max_age_minutes=10)
    refresh_in_progress = data_cache.update_in_progress
    
    # Handle stale data
    if is_stale:
        # If requested to wait for fresh data or if data is critically stale
        if wait_for_fresh or data_cache.is_critically_stale():
            logger.info("Waiting for fresh data...")
            
            # If no refresh is in progress, start one
            if not refresh_in_progress:
                # Reset the update event and start a refresh
                data_cache.reset_update_event()
                await refresh_data_cache(background_tasks, force=True)
            
            # Wait for the update to complete with timeout
            success = await data_cache.wait_for_update()
            
            if not success:
                logger.warning("Timeout waiting for fresh data, returning potentially stale data")
        else:
            # Schedule background refresh if not already in progress
            if not refresh_in_progress:
                logger.info("Cache is stale. Scheduling background refresh.")
                background_tasks.add_task(refresh_data_cache, background_tasks)
    
    # If we get here, we have some data to return (potentially stale)
    # Add cache information to the response
    result = data_cache.fire_risk_data.copy()
    result["cache_info"] = {
        # The isoformat() will include timezone info for timezone-aware datetimes
        "last_updated": data_cache.last_updated.isoformat() if data_cache.last_updated else None,
        "is_fresh": not data_cache.is_stale(max_age_minutes=10),
        "refresh_in_progress": data_cache.update_in_progress,
        "using_cached_data": data_cache.using_cached_data
    }
    
    # Add field-level caching information to the response
    # If we're using cached data from a previous successful API call (fallback mode)
    if data_cache.using_cached_data:
        # Add field-specific cache information
        current_time = datetime.now(TIMEZONE)
        
        # Calculate how old the data is
        if data_cache.last_valid_data["timestamp"]:
            cached_time = data_cache.last_valid_data["timestamp"]
            age_str = format_age_string(current_time, cached_time)
            
            # Add cached_data field to the response
            result["cached_data"] = {
                "is_cached": True,
                "original_timestamp": cached_time.isoformat(),
                "age": age_str,
                "cached_fields": data_cache.cached_fields.copy() # Use a copy
            }

            # --- START NEW CODE ---
            # Ensure the weather data in the result reflects the cached values
            if "weather" in result and "weather" in data_cache.last_valid_data:
                cached_weather = data_cache.last_valid_data["weather"]
                target_weather = result["weather"]
                cached_fields_map = data_cache.cached_fields # The flags set by cache_refresh

                # Map internal cache field names to response field names
                field_mapping = {
                    "temperature": "air_temp",
                    "humidity": "relative_humidity",
                    "wind_speed": "wind_speed",
                    "wind_gust": "wind_gust",
                    "soil_moisture": "soil_moisture_15cm"
                }

                for cache_field_name, use_cached in cached_fields_map.items():
                    if use_cached:
                        response_field_name = field_mapping.get(cache_field_name)
                        # Check if the cached value exists in last_valid_data
                        if response_field_name and response_field_name in cached_weather:
                            cached_value = cached_weather.get(response_field_name)
                            # Only update if the cached value is not None
                            if cached_value is not None:
                                target_weather[response_field_name] = cached_value
                                logger.debug(f"Endpoint: Merged cached value for {response_field_name}: {cached_value}")
                            else:
                                logger.warning(f"Endpoint: Cached flag set for {response_field_name}, but no value found in last_valid_data.")
                        else:
                             logger.warning(f"Endpoint: Cannot map cache field '{cache_field_name}' or field missing in cached_weather.")

            # --- END NEW CODE ---
            
            # Make sure the explanation includes the notice about cached data
            if "explanation" in result and "NOTICE: Displaying cached data" not in result["explanation"]:
                result["explanation"] += f" NOTICE: Displaying cached data from {cached_time.strftime('%Y-%m-%d %H:%M')} ({age_str} old)."
    
    return result

@router.get("/", response_class=HTMLResponse)
def home():
    """Fire Risk Dashboard with Synoptic Data Attribution and Dynamic Timestamp"""
    # Read the dashboard HTML file
    dashboard_path = pathlib.Path("static/dashboard.html")
    if dashboard_path.exists():
        with open(dashboard_path, "r") as f:
            return f.read()
    else:
        # Fallback if file doesn't exist
        return """<!DOCTYPE html>
<html>
<head>
    <title>Dashboard Not Found</title>
</head>
<body>
    <h1>Dashboard file not found</h1>
    <p>The dashboard HTML file could not be loaded.</p>
</body>
</html>"""

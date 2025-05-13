from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Cookie
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Dict, Any, Optional
import os
import pathlib
from datetime import datetime

from config import logger, TIMEZONE
from cache import data_cache
from cache_refresh import refresh_data_cache
from data_processing import format_age_string
from admin_endpoints import admin_sessions # Import admin_sessions

# Create a router for the main endpoints
router = APIRouter()


@router.get("/fire-risk")
async def fire_risk(
    request: Request, # Add request object
    background_tasks: BackgroundTasks, 
    wait_for_fresh: bool = False,
    session_token: Optional[str] = Cookie(None) # Get session_token from cookie
):
    """API endpoint to fetch fire risk status.
    
    Args:
        request: The FastAPI Request object.
        background_tasks: FastAPI BackgroundTasks for scheduling refreshes
        wait_for_fresh: If True, wait for fresh data instead of returning stale data
        session_token: Admin session token from cookie.
    """
    # First-time fetch (cache empty)
    if data_cache.fire_risk_data is None:
        logger.info("Initial data fetch (cache empty)")
        # Pass session_token and admin_sessions to refresh_data_cache
        await refresh_data_cache(
            background_tasks, 
            session_token=session_token, 
            current_admin_sessions=admin_sessions
        )
        
        # If still no data after refresh, we have a problem
        if data_cache.fire_risk_data is None:
            logger.error("No data available in cache after refresh attempt")
            raise HTTPException(
                status_code=503,
                detail="Weather data service unavailable. Please try again later."
            )
    
    # Check if data is stale (using 60-minute threshold)
    is_stale = data_cache.is_stale(max_age_minutes=60)
    refresh_in_progress = data_cache.update_in_progress
    
    # Initialize timeout flag
    timed_out_waiting_for_fresh = False
    
    # Handle stale data OR if wait_for_fresh is explicitly requested
    if wait_for_fresh or is_stale: # MODIFIED: Always enter this block if wait_for_fresh is true
            # If requested to wait for fresh data, or if data is stale (critically or normally)
            if wait_for_fresh or data_cache.is_critically_stale() or is_stale: # Ensure logic inside still makes sense
                logger.info(f"Condition for refresh met: wait_for_fresh={wait_for_fresh}, is_stale={is_stale}, critically_stale={data_cache.is_critically_stale()}")
                
                # If no refresh is in progress, start one
                if not refresh_in_progress:
                    logger.info("No refresh in progress, initiating a forced refresh")
                    # Reset the update event and start a refresh
                    data_cache.reset_update_event()
                    refresh_started = await refresh_data_cache(
                        background_tasks, 
                        force=True,
                        session_token=session_token,
                        current_admin_sessions=admin_sessions
                    )
                    logger.info(f"Forced refresh started: {refresh_started}")
                else:
                    logger.info("Refresh already in progress, waiting for it to complete")
                
                # Log cached field status before waiting
                logger.info(f"Cached fields before wait: {data_cache.cached_fields}")
                
                # Wait for the update to complete with timeout
                logger.info("Waiting for update event with timeout...")
                success = await data_cache.wait_for_update()
                logger.info(f"Wait for update completed with success={success}")

                # Log cached field status after waiting
                logger.info(f"Cached fields after wait: {data_cache.cached_fields}")
                
                # Check specifically for wind gust data
                if "wind_gust" in data_cache.cached_fields:
                    logger.info(f"Wind gust data is using cache: {data_cache.cached_fields['wind_gust']}")
                    
                    # If from last_valid_data, log the value and timestamp
                    if data_cache.cached_fields['wind_gust'] and "fields" in data_cache.last_valid_data:
                        wind_field = data_cache.last_valid_data["fields"].get("wind_gust", {})
                        wind_value = wind_field.get("value")
                        wind_timestamp = wind_field.get("timestamp")
                        logger.info(f"Cached wind gust value: {wind_value}, timestamp: {wind_timestamp}")

                timed_out_waiting_for_fresh = False # Flag to track timeout specifically in wait_for_fresh path
                if not success:
                    logger.warning("⚠️ Timeout waiting for fresh data, returning potentially stale data")
                    logger.warning("This will trigger 'Refresh failed' in the UI")
                    timed_out_waiting_for_fresh = True # Set the flag
            else:
                # Schedule background refresh if not already in progress
                if not refresh_in_progress:
                    logger.info("Cache is stale. Scheduling background refresh.")
                    # Pass session_token and admin_sessions to background task
                    background_tasks.add_task(
                        refresh_data_cache, 
                        background_tasks, # This is the first arg for refresh_data_cache
                        session_token=session_token, 
                        current_admin_sessions=admin_sessions
                    )
    
    # If we get here, we have some data to return (potentially stale)
    # Add cache information to the response
    result = data_cache.fire_risk_data.copy()
    result["cache_info"] = {
        # The isoformat() will include timezone info for timezone-aware datetimes
        "last_updated": data_cache.last_updated.isoformat() if data_cache.last_updated else None,
        "is_fresh": not data_cache.is_stale(max_age_minutes=60), # Use 60-minute threshold
        "refresh_in_progress": data_cache.update_in_progress,
        "using_cached_data": data_cache.using_cached_data # Initial value from global state
    }

    # If we specifically timed out while waiting for fresh data, override the flag in the response
    if timed_out_waiting_for_fresh:
        result["cache_info"]["using_cached_data"] = True
        result["cache_info"]["wait_for_fresh_timed_out"] = True  # Add explicit flag indicating timeout
        
        # Log detailed information about the timeout for debugging
        logger.warning(f"⚠️ wait_for_fresh request timed out - returning cached data with timeout flag")
        logger.info(f"Cached fields state at timeout: {data_cache.cached_fields}")

    # Add threshold values from config to the response
    from config import THRESH_TEMP, THRESH_HUMID, THRESH_WIND, THRESH_GUSTS, THRESH_SOIL_MOIST
    result["thresholds"] = {
        "temp": THRESH_TEMP,
        "humid": THRESH_HUMID,
        "wind": THRESH_WIND,
        "gusts": THRESH_GUSTS,
        "soil_moist": THRESH_SOIL_MOIST
    }
    
    # Ensure all weather metrics have values (never return None)
    if result and "weather" in result:
        # This method now also updates data_cache.cached_fields and data_cache.using_cached_data
        result["weather"] = data_cache.ensure_complete_weather_data(result["weather"])
        
        # Initialize cached_fields in the result weather data if it doesn't exist
        if "cached_fields" not in result["weather"]:
            result["weather"]["cached_fields"] = {}
            
        # Ensure the timestamp sub-object exists
        if "timestamp" not in result["weather"]["cached_fields"]:
             result["weather"]["cached_fields"]["timestamp"] = {}

        # Populate the timestamp object based on the cached_fields flags
        for field_name, is_cached in data_cache.cached_fields.items():
            if is_cached:
                # Add the boolean flag (for potential future use or clarity)
                result["weather"]["cached_fields"][field_name] = True
                # Add the timestamp from last_valid_data
                if field_name in data_cache.last_valid_data["fields"]:
                    timestamp = data_cache.last_valid_data["fields"][field_name].get("timestamp")
                    if timestamp:
                        result["weather"]["cached_fields"]["timestamp"][field_name] = timestamp.isoformat()
            else:
                 # Ensure boolean flag is set to false if not cached
                 result["weather"]["cached_fields"][field_name] = False

        # Update the main cache_info in the result based on the final state
        result["cache_info"]["using_cached_data"] = data_cache.using_cached_data
        result["cache_info"]["cached_fields"] = data_cache.cached_fields.copy() # Add the flags here too
            
    # Add field-level caching information to the response (This block might be redundant now)
    # Check the flag *in the result* now, not just the global state
    if result["cache_info"]["using_cached_data"]:
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

            # Ensure weather data has the cached_fields structure
            if "weather" in result:
                if "cached_fields" not in result["weather"]:
                    result["weather"]["cached_fields"] = {}
                
                # Copy the cached_fields structure with proper flags
                result["weather"]["cached_fields"] = data_cache.cached_fields.copy()
                
                # Add timestamp information for each field
                if "timestamp" not in result["weather"]["cached_fields"]:
                    result["weather"]["cached_fields"]["timestamp"] = {}
                
                # Add timestamps for all cached fields
                for field_name, is_cached in data_cache.cached_fields.items():
                    if is_cached and field_name in data_cache.last_valid_data["fields"]:
                        field_timestamp = data_cache.last_valid_data["fields"][field_name].get("timestamp")
                        if field_timestamp:
                            result["weather"]["cached_fields"]["timestamp"][field_name] = field_timestamp.isoformat()
                
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

            # Prepare content for the data status modal
            modal_content = {
                "note": None,
                "warning_title": None,
                "warning_issues": []
            }
            modal_content["note"] = "Displaying cached weather data. Current data is unavailable."

            # Check for data quality issues from the original (cached) data
            if "weather" in data_cache.last_valid_data and \
               "data_status" in data_cache.last_valid_data["weather"] and \
               data_cache.last_valid_data["weather"]["data_status"].get("issues"):
                
                issues = data_cache.last_valid_data["weather"]["data_status"]["issues"]
                if issues:
                    modal_content["warning_title"] = "Data Quality Warning (from cached data):"
                    modal_content["warning_issues"] = issues
            
            # Set the note specifically because we know we fell back to cache
            modal_content["note"] = "Displaying cached weather data. Current data is unavailable."

            # Check for data quality issues from the original (cached) data
            if "weather" in data_cache.last_valid_data and \
               "data_status" in data_cache.last_valid_data["weather"] and \
               data_cache.last_valid_data["weather"]["data_status"].get("issues"):

                issues = data_cache.last_valid_data["weather"]["data_status"]["issues"]
                if issues:
                    modal_content["warning_title"] = "Data Quality Warning (from cached data):"
                    modal_content["warning_issues"] = issues

            result["modal_content"] = modal_content

    # If not using cached data, check for current data quality issues
    elif "weather" in result and "data_status" in result["weather"] and result["weather"]["data_status"].get("issues"):
         issues = result["weather"]["data_status"]["issues"]
         if issues:
             result["modal_content"] = {
                 "note": None,
                 "warning_title": "Data Quality Warning:",
                 "warning_issues": issues
             }
    else:
        # Ensure modal_content exists even if there are no issues
        result["modal_content"] = {
            "note": None,
            "warning_title": None,
            "warning_issues": []
        }

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
# Router is included in main.py, not here
# app.include_router(router)


@router.get("/toggle-test-mode", response_class=JSONResponse)
async def toggle_test_mode_endpoint( # Renamed to avoid conflict with admin_endpoints toggle_test_mode if routes are merged
    request: Request, # Add request
    background_tasks: BackgroundTasks, 
    enable: bool = False,
    session_token: Optional[str] = Cookie(None) # Add session_token
):
    """Toggle test mode on or off via API


    
    This endpoint is designed to be called from JavaScript in the dashboard UI.
    When enabled, it will force the system to use cached data (simulate API failure).
    When disabled, it will restore normal operation.
    
    Args:
        background_tasks: FastAPI BackgroundTasks for scheduling refreshes
        enable: If True, enable test mode (use cached data); if False, disable test mode
    
    Returns:
        JSON response with the status of the test mode toggle
    """
    if enable:
        # First check if we have cached data
        if data_cache.last_valid_data["timestamp"] is None:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "No cached data available yet. Please visit the dashboard first to populate the cache."}
            )
        
        # Set the flag to use cached data
        data_cache.using_cached_data = True
        
        # Set all cached fields to true since we're using all cached data
        for field in data_cache.cached_fields:
            data_cache.cached_fields[field] = True
            
        logger.info("🔵 TEST MODE: Enabled via UI toggle")
        
        # Get timestamp information for display
        from datetime import datetime
        from config import TIMEZONE
        from data_processing import format_age_string
        
        current_time = datetime.now(TIMEZONE)
        cached_time = data_cache.last_valid_data["timestamp"]
        
        # Calculate age of data
        age_str = format_age_string(current_time, cached_time)
        
        # Update the cached fire risk data
        if data_cache.fire_risk_data:
            cached_fire_risk_data = data_cache.last_valid_data["fire_risk_data"].copy()
            
            # Add timestamps to each cached field to ensure age indicators appear
            if 'weather' in cached_fire_risk_data:
                # Ensure there's a cached_fields structure
                if not 'cached_fields' in cached_fire_risk_data['weather']:
                    cached_fire_risk_data['weather']['cached_fields'] = {}
                
                # In test mode, force all fields to be marked as cached
                cached_fire_risk_data['weather']['cached_fields'] = {
                    'temperature': True,
                    'humidity': True,
                    'wind_speed': True,
                    'soil_moisture': True,
                    'wind_gust': True,
                    'timestamp': {
                        'temperature': cached_time.isoformat(),
                        'humidity': cached_time.isoformat(),
                        'wind_speed': cached_time.isoformat(),
                        'soil_moisture': cached_time.isoformat(),
                        'wind_gust': cached_time.isoformat()
                    }
                }
                
                # Add note to modal content
                cached_fire_risk_data['modal_content'] = {
                    'note': 'Displaying cached weather data. Current data is unavailable.',
                    'warning_title': 'Test Mode Active',
                    'warning_issues': ['This is a test of the caching system. All data shown is from cache.']
                }
            
            cached_fire_risk_data["cached_data"] = {
                "is_cached": True,
                "original_timestamp": cached_time.isoformat(),
                "age": age_str
            }
            
            # Update the cache
            data_cache.fire_risk_data = cached_fire_risk_data
        
        return JSONResponse(
            content={"status": "success", "mode": "test", "message": "Test mode enabled. Using cached data."}
        )
    else:
        # Disable test mode and return to normal operation
        data_cache.using_cached_data = False
        
        # Reset all cached field flags to False
        for field in data_cache.cached_fields:
            data_cache.cached_fields[field] = False
        
        # Reset the fire risk data to remove any cached data indicators
        if data_cache.fire_risk_data and "cached_data" in data_cache.fire_risk_data:
            # Remove the cached_data field
            fire_risk_copy = data_cache.fire_risk_data.copy()
            del fire_risk_copy["cached_data"]
            
            # Remove any cached data mentions from the explanation
            if "explanation" in fire_risk_copy:
                explanation = fire_risk_copy["explanation"]
                if "NOTICE: Displaying cached data" in explanation:
                    explanation = explanation.split(" NOTICE: Displaying cached data")[0]
                    fire_risk_copy["explanation"] = explanation
                    
            # Update the fire risk data
            data_cache.fire_risk_data = fire_risk_copy
        
        # Force a refresh with fresh data
        logger.info("🔵 TEST MODE: Disabled via UI toggle")
        refresh_success = await refresh_data_cache(
            background_tasks, 
            force=True,
            session_token=session_token, # Pass session token
            current_admin_sessions=admin_sessions # Pass admin_sessions
        )
        
        return JSONResponse(
            content={
                "status": "success", 
                "mode": "normal", 
                "refresh_success": refresh_success,
                "message": "Test mode disabled. Returned to normal operation."
            }
        )

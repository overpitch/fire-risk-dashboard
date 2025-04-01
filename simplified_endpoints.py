from fastapi import FastAPI, APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Dict, Any
import os
import pathlib
from datetime import datetime

from config import logger, TIMEZONE
from simplified_cache import data_cache
from simplified_cache_refresh import refresh_data_cache
from data_processing import format_age_string

# Create the FastAPI app
app = FastAPI()

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
    if not data_cache.current_snapshot:
        logger.info("Initial data fetch (cache empty)")
        await refresh_data_cache(background_tasks)
        
        # If still no data after refresh, we have a problem
        if not data_cache.current_snapshot:
            logger.error("No data available after refresh attempt")
            raise HTTPException(
                status_code=503,
                detail="Weather data service unavailable. Please try again later."
            )
    
    # Check if data is stale (using 60-minute threshold for "staleness")
    is_stale = data_cache.is_stale(max_age_minutes=60)
    refresh_in_progress = data_cache.update_in_progress
    
    # If user wants to wait for fresh data and the data is stale
    if wait_for_fresh and is_stale:
        logger.info("Client requested to wait for fresh data...")
        
        # If no refresh is in progress, start one
        if not refresh_in_progress:
            data_cache.reset_update_event()
            await refresh_data_cache(background_tasks, force=True)
        
        # Wait for the update to complete with timeout
        success = await data_cache.wait_for_update()
        
        if not success:
            logger.warning("Timeout waiting for fresh data, returning cached data")
            # Mark as using cached data since the refresh timed out
            data_cache.using_cached_data = True
    elif is_stale and not refresh_in_progress:
        # Schedule background refresh if data is stale but client didn't request to wait
        logger.info("Cache is stale. Scheduling background refresh.")
        background_tasks.add_task(refresh_data_cache, background_tasks)
    
    # Get the current snapshot data
    current_data = data_cache.get_latest_data()
    if not current_data or "fire_risk_data" not in current_data:
        logger.error("Current snapshot missing fire_risk_data")
        raise HTTPException(
            status_code=500,
            detail="Internal server error: Data snapshot corrupted"
        )
    
    # Create a copy of the fire risk data to modify for the response
    result = current_data["fire_risk_data"].copy()
    
    # Add cache information to the response
    result["cache_info"] = {
        "last_updated": data_cache.last_updated.isoformat() if data_cache.last_updated else None,
        "is_fresh": not is_stale,
        "refresh_in_progress": data_cache.update_in_progress,
        "using_cached_data": data_cache.using_cached_data
    }
    
    # Include snapshot timestamp (critical for transparency)
    if "timestamp" in current_data:
        result["cache_info"]["snapshot_timestamp"] = current_data["timestamp"].isoformat()
    
    # If using cached data, add clear indicators and age information
    if data_cache.using_cached_data:
        current_time = datetime.now(TIMEZONE)
        
        # Calculate age based on snapshot timestamp
        if "timestamp" in current_data:
            snapshot_time = current_data["timestamp"]
            age_str = format_age_string(current_time, snapshot_time)
            
            # Add cached_data field with clear age indicators
            result["cached_data"] = {
                "is_cached": True,
                "original_timestamp": snapshot_time.isoformat(),
                "age": age_str
            }
            
            # Add modal content for UI to clearly show cached status
            result["modal_content"] = {
                "note": f"⚠️ Displaying cached weather data from {age_str} ago. Current data is unavailable.",
                "warning_title": "Using Cached Data",
                "warning_issues": ["Unable to fetch fresh data from weather APIs."]
            }
    
    # Add threshold values from config to the response
    from config import THRESH_TEMP, THRESH_HUMID, THRESH_WIND, THRESH_GUSTS, THRESH_SOIL_MOIST
    result["thresholds"] = {
        "temp": THRESH_TEMP,
        "humid": THRESH_HUMID,
        "wind": THRESH_WIND,
        "gusts": THRESH_GUSTS,
        "soil_moist": THRESH_SOIL_MOIST
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

@router.get("/toggle-test-mode", response_class=JSONResponse)
async def toggle_test_mode(background_tasks: BackgroundTasks, enable: bool = False):
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
        # First check if we have a snapshot available
        if not data_cache.current_snapshot:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "No cached data available yet. Please visit the dashboard first to populate the cache."}
            )
        
        # Set the flag to use cached data
        data_cache.using_cached_data = True
        
        logger.info("🔵 TEST MODE: Enabled via UI toggle")
        
        # Get timestamp information for display
        current_time = datetime.now(TIMEZONE)
        
        # Get snapshot timestamp
        snapshot_time = data_cache.current_snapshot.get("timestamp", current_time)
        age_str = format_age_string(current_time, snapshot_time)
        
        # Update the modal content to indicate test mode
        if "fire_risk_data" in data_cache.current_snapshot:
            fire_risk_copy = data_cache.current_snapshot["fire_risk_data"].copy()
            
            # Add snapshot age information
            fire_risk_copy["cached_data"] = {
                "is_cached": True,
                "original_timestamp": snapshot_time.isoformat(),
                "age": age_str
            }
            
            # Add test mode modal content
            fire_risk_copy["modal_content"] = {
                "note": f"⚠️ TEST MODE: Displaying cached weather data from {age_str} ago.",
                "warning_title": "Test Mode Active",
                "warning_issues": ["This is a test of the caching system. All data shown is from cache."]
            }
            
            # Update the fire risk data
            data_cache.current_snapshot["fire_risk_data"] = fire_risk_copy
        
        return JSONResponse(
            content={"status": "success", "mode": "test", "message": "Test mode enabled. Using cached data."}
        )
    else:
        # Disable test mode and return to normal operation
        data_cache.using_cached_data = False
        
        # Force a refresh with fresh data
        logger.info("🔵 TEST MODE: Disabled via UI toggle")
        refresh_success = await refresh_data_cache(background_tasks, force=True)
        
        return JSONResponse(
            content={
                "status": "success", 
                "mode": "normal", 
                "refresh_success": refresh_success,
                "message": "Test mode disabled. Returned to normal operation."
            }
        )

# Include the router in the app
app.include_router(router)

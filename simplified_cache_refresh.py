import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from fastapi import BackgroundTasks

from config import TIMEZONE, logger
from api_clients import get_synoptic_data
from data_processing import combine_weather_data, format_age_string
from fire_risk_logic import calculate_fire_risk
from simplified_cache import data_cache

async def refresh_data_cache(background_tasks: Optional[BackgroundTasks] = None, 
                           force: bool = False) -> bool:
    """Refresh the data cache with an all-or-nothing approach.
    
    Args:
        background_tasks: Optional BackgroundTasks for scheduling future refreshes
        force: Force refresh even if an update is already in progress
    
    Returns:
        bool: True if refresh was successful, False otherwise
    """
    # Reset the update complete event
    data_cache.reset_update_event()
    
    # If an update is in progress and we're not forcing a refresh, skip
    if data_cache.update_in_progress and not force:
        logger.info("Data refresh already in progress, skipping...")
        return False
    
    # Acquire update lock
    data_cache.update_in_progress = True
    logger.info("Starting data cache refresh using snapshot approach...")
    
    success = False
    start_time = time.time()
    
    try:
        # Fetch all data concurrently
        synoptic_data, wunderground_data = await fetch_all_data()
        
        # Only consider the refresh successful if we get ALL data
        if synoptic_data is not None and wunderground_data is not None:
            # Both APIs succeeded, create a complete snapshot
            
            # Process the API responses to get complete weather data
            latest_weather = combine_weather_data(synoptic_data, wunderground_data)
            
            # Calculate fire risk based on the latest weather data
            risk, explanation = calculate_fire_risk(latest_weather)
            
            # Create the complete fire risk data package that matches UI expectations
            fire_risk_data = {
                "risk": risk, 
                "explanation": explanation, 
                "weather": latest_weather,
                "cached_data": None  # Will be added by endpoints.py when needed
            }
            
            # Update the cache with the new complete snapshot
            data_cache.update_cache(synoptic_data, wunderground_data, fire_risk_data)
            success = True
            
            # Log success with actual values for verification
            logger.info(f"✅ Snapshot refresh SUCCESSFUL - Wind speed: {latest_weather.get('wind_speed')} mph")
        else:
            # At least one API failed, we'll keep using the existing snapshot
            logger.warning("❌ Snapshot refresh FAILED - Some APIs returned incomplete data")
            
            # Log details about which API failed
            if synoptic_data is None:
                logger.error("Failed to fetch data from Synoptic API")
            if wunderground_data is None:
                logger.error("Failed to fetch data from Weather Underground API")
            
            # Mark that we are using cached data
            data_cache.using_cached_data = True
            success = False
            
            # Log the values from current cached data for debugging
            current_data = data_cache.get_latest_data()
            if current_data and "fire_risk_data" in current_data and "weather" in current_data["fire_risk_data"]:
                cached_weather = current_data["fire_risk_data"]["weather"]
                logger.info(f"🔄 Using cached data - Wind speed: {cached_weather.get('wind_speed')} mph")
    
    except Exception as e:
        # Log any exceptions during refresh
        logger.error(f"Error during cache refresh: {str(e)}")
        data_cache.using_cached_data = True
        success = False
    
    # Calculate refresh time for logging
    refresh_time = time.time() - start_time
    logger.info(f"Data refresh completed in {refresh_time:.2f} seconds")
    
    # Update metadata
    data_cache.update_in_progress = False
    data_cache.last_update_success = success
    
    # Schedule next refresh if running as a background task
    if background_tasks and not data_cache.refresh_task_active:
        # Schedule the next refresh based on the optimal timing for SEYC1 updates
        background_tasks.add_task(schedule_next_refresh)
        data_cache.refresh_task_active = True
        
    return success

async def fetch_all_data() -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Fetch all data concurrently using asyncio.
    
    Returns:
        Tuple of (synoptic_data, wunderground_data)
    """
    # Create tasks for both API calls
    loop = asyncio.get_running_loop()
    
    # Define functions to run in thread pool
    def fetch_synoptic():
        return get_synoptic_data()
        
    def fetch_wunderground():
        return None  # Weather Underground data no longer used
    
    # Run both API calls concurrently in thread pool
    try:
        weather_data_task = loop.run_in_executor(None, fetch_synoptic)
        wunderground_data_task = loop.run_in_executor(None, fetch_wunderground)
        
        # Wait for both tasks to complete with timeout
        weather_data, wunderground_data = await asyncio.gather(
            weather_data_task,
            wunderground_data_task,
            return_exceptions=True
        )
        
        # Check for exceptions
        if isinstance(weather_data, Exception):
            logger.error(f"Error fetching Synoptic data: {weather_data}")
            weather_data = None
            
        if isinstance(wunderground_data, Exception):
            logger.error(f"Error fetching Weather Underground data: {wunderground_data}")
            wunderground_data = None
        
        return weather_data, wunderground_data
            
    except Exception as e:
        logger.error(f"Error during concurrent data fetch: {e}")
        return None, None

def get_next_refresh_delay() -> int:
    """Calculate minutes until next scheduled refresh at :20, :40, or :00.
    
    The SEYC1 weather station updates on the quarter-hour (:00, :15, :30, :45),
    so we fetch at :20, :40, and :00 to get data ~5 minutes after it updates.
    
    Returns:
        int: Minutes until the next scheduled refresh time
    """
    now = datetime.now(TIMEZONE)
    
    # Get minutes component of current time
    current_minute = now.minute
    
    # Calculate minutes until next scheduled refresh
    if current_minute < 20:
        # Wait until XX:20
        return 20 - current_minute
    elif current_minute < 40:
        # Wait until XX:40
        return 40 - current_minute
    else:
        # Wait until the next hour's XX:00
        return 60 - current_minute

async def schedule_next_refresh(minutes: Optional[int] = None):
    """Schedule the next refresh at the optimal time.
    
    Args:
        minutes: Optional override for refresh delay. If not provided,
                will calculate optimal time based on SEYC1 update schedule.
    """
    try:
        # If minutes is not provided, calculate optimal timing
        if minutes is None:
            minutes = get_next_refresh_delay()
            
        logger.info(f"Scheduling next background refresh in {minutes} minutes "
                   f"(at {(datetime.now(TIMEZONE) + timedelta(minutes=minutes)).strftime('%H:%M:%S')})")
        
        await asyncio.sleep(minutes * 60)
        await refresh_data_cache()
    except Exception as e:
        logger.error(f"Error in scheduled refresh: {e}")
    finally:
        # Reset the refresh task flag so we can schedule again
        data_cache.refresh_task_active = False

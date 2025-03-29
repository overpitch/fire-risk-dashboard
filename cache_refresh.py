import asyncio
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from fastapi import BackgroundTasks

from config import TIMEZONE, logger
from api_clients import get_synoptic_data, get_wunderground_data
from config import WUNDERGROUND_STATION_IDS
from data_processing import combine_weather_data, format_age_string
from fire_risk_logic import calculate_fire_risk
from cache import data_cache

async def refresh_data_cache(background_tasks: Optional[BackgroundTasks] = None, force: bool = False) -> bool:
    """Refresh the data cache by fetching new data from APIs.
    
    Args:
        background_tasks: Optional BackgroundTasks for scheduling future refreshes
        force: Force refresh even if an update is already in progress
    
    Returns:
        bool: True if refresh was successful, False otherwise
    """
    # Reset the update complete event before starting a new update
    data_cache.reset_update_event()
    
    # If an update is in progress and we're not forcing a refresh, skip
    if data_cache.update_in_progress and not force:
        logger.info("Data refresh already in progress, skipping...")
        return False
    
    # Acquire update lock
    data_cache.update_in_progress = True
    logger.info("Starting data cache refresh...")
    
    success = False
    retries = 0
    start_time = time.time()
    
    async def fetch_all_data():
        """Fetch all data concurrently using asyncio."""
        # Create tasks for both API calls
        loop = asyncio.get_running_loop()
        
        # Define functions to run in thread pool
        def fetch_synoptic():
            return get_synoptic_data()
            
        def fetch_wunderground():
            # Get data for all stations
            return get_wunderground_data()
        
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
            else:
                # Log summary of station data
                if wunderground_data:
                    successful_stations = [station_id for station_id, data in wunderground_data.items() if data is not None]
                    failed_stations = [station_id for station_id, data in wunderground_data.items() if data is None]
                    
                    if successful_stations:
                        logger.info(f"Successfully fetched data from {len(successful_stations)} Weather Underground stations: {', '.join(successful_stations)}")
                    if failed_stations:
                        logger.warning(f"Failed to fetch data from {len(failed_stations)} Weather Underground stations: {', '.join(failed_stations)}")
                
            return weather_data, wunderground_data
                
        except Exception as e:
            logger.error(f"Error during concurrent data fetch: {e}")
            return None, None
    
    while not success and retries < data_cache.max_retries:
        try:
            # Check if we're exceeding our total timeout
            if time.time() - start_time > data_cache.update_timeout:
                logger.warning(f"Data refresh taking too long (over {data_cache.update_timeout}s), aborting")
                break
                
            # Fetch data from both APIs concurrently
            weather_data, wunderground_data = await fetch_all_data()
            
            # Initialize variables for tracking cached data usage
            any_field_using_cache = False
            cached_fields_info = []
            
            # Process the API responses to get the latest weather data
            latest_weather = combine_weather_data(weather_data, wunderground_data, data_cache.cached_fields)
            
            # Ensure all weather data fields have values using the new method
            # This will fill in any missing values with cached data or defaults
            latest_weather = data_cache.ensure_complete_weather_data(latest_weather)
            
            # Track if we're using any cached values
            any_field_using_cache = any(data_cache.cached_fields.values())
            data_cache.using_cached_data = any_field_using_cache
            
            # Log which fields are using cached data for debugging
            if any_field_using_cache:
                current_time = datetime.now(TIMEZONE)
                cached_fields_info = []
                
                # Map between internal field names and API response field names
                field_mapping = {
                    "temperature": "air_temp",
                    "humidity": "relative_humidity",
                    "wind_speed": "wind_speed",
                    "soil_moisture": "soil_moisture_15cm",
                    "wind_gust": "wind_gust"
                }
                
                # Log information about each cached field
                for internal_field, is_cached in data_cache.cached_fields.items():
                    if is_cached:
                        api_field = field_mapping.get(internal_field)
                        value = latest_weather.get(api_field)
                        cached_time = data_cache.last_valid_data["fields"][internal_field]["timestamp"]
                        age_str = format_age_string(current_time, cached_time)
                        
                        logger.info(f"Using cached {internal_field} data: {value} from {cached_time.isoformat()} ({age_str} old)")
                        
                        # Store info about this cached field
                        cached_fields_info.append({
                            "field": internal_field,
                            "value": value,
                            "timestamp": cached_time,
                            "age": age_str
                        })
            
            # Calculate fire risk based on the latest weather data
            risk, explanation = calculate_fire_risk(latest_weather)
            
            # Explanation is now just the base risk explanation from calculate_fire_risk
            # Notes about data issues or cached values are handled by the modal content in endpoints.py
            
            fire_risk_data = {"risk": risk, "explanation": explanation, "weather": latest_weather}
            
            # If we're using cached data, add the cached_data field
            if any_field_using_cache:
                # Get timestamp information for display
                cached_time = data_cache.last_valid_data["timestamp"]
                
                # Calculate age of data
                age_str = format_age_string(current_time, cached_time)
                
                # Add cached_data field to fire_risk_data
                fire_risk_data["cached_data"] = {
                    "is_cached": True,
                    "original_timestamp": cached_time.isoformat(),
                    "age": age_str,
                    "cached_fields": data_cache.cached_fields.copy()
                }
            
            # Update cache with new data
            data_cache.update_cache(weather_data, wunderground_data, fire_risk_data)
            
            # If we got here, the refresh was successful
            success = True
            logger.info("Data cache refresh successful")
            
        except Exception as e:
            retries += 1
            logger.error(f"Error refreshing data cache (attempt {retries}/{data_cache.max_retries}): {str(e)}")
            if retries < data_cache.max_retries:
                logger.info(f"Retrying in {data_cache.retry_delay} seconds...")
                await asyncio.sleep(data_cache.retry_delay)
    
    data_cache.update_in_progress = False
    data_cache.last_update_success = success
    
    if not success:
        logger.error("All data refresh attempts failed")
    
    # Schedule next refresh if running as a background task
    if background_tasks and not data_cache.refresh_task_active:
        # Schedule the next refresh based on the configured interval
        background_tasks.add_task(schedule_next_refresh, data_cache.background_refresh_interval)
        data_cache.refresh_task_active = True
        
    return success

async def schedule_next_refresh(minutes: int):
    """Schedule the next refresh after a delay."""
    try:
        logger.info(f"Scheduling next background refresh in {minutes} minutes")
        await asyncio.sleep(minutes * 60)
        await refresh_data_cache()
    except Exception as e:
        logger.error(f"Error in scheduled refresh: {e}")
    finally:
        # Reset the refresh task flag so we can schedule again
        data_cache.refresh_task_active = False

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
            
            # Check for missing fields and use cached values if available
            current_time = datetime.now(TIMEZONE)
            
            # Check for individual fields that are missing and use cached values where available
            if latest_weather["air_temp"] is None and data_cache.last_valid_data["fields"]["temperature"]["value"] is not None:
                latest_weather["air_temp"] = data_cache.last_valid_data["fields"]["temperature"]["value"]
                data_cache.cached_fields["temperature"] = True
                any_field_using_cache = True
                
                cached_time = data_cache.last_valid_data["fields"]["temperature"]["timestamp"]
                age_str = format_age_string(current_time, cached_time)
                
                logger.info(f"Using cached temperature data: {latest_weather['air_temp']}°C from {cached_time.isoformat()} ({age_str} old)")
                
                # Store info about this cached field
                cached_fields_info.append({
                    "field": "temperature",
                    "value": latest_weather["air_temp"],
                    "timestamp": cached_time,
                    "age": age_str
                })
            
            if latest_weather["relative_humidity"] is None and data_cache.last_valid_data["fields"]["humidity"]["value"] is not None:
                latest_weather["relative_humidity"] = data_cache.last_valid_data["fields"]["humidity"]["value"]
                data_cache.cached_fields["humidity"] = True
                any_field_using_cache = True
                
                cached_time = data_cache.last_valid_data["fields"]["humidity"]["timestamp"]
                age_str = format_age_string(current_time, cached_time)
                
                logger.info(f"Using cached humidity data: {latest_weather['relative_humidity']}% from {cached_time.isoformat()} ({age_str} old)")
                
                # Store info about this cached field
                cached_fields_info.append({
                    "field": "humidity",
                    "value": latest_weather["relative_humidity"],
                    "timestamp": cached_time,
                    "age": age_str
                })
            
            if latest_weather["wind_speed"] is None and data_cache.last_valid_data["fields"]["wind_speed"]["value"] is not None:
                latest_weather["wind_speed"] = data_cache.last_valid_data["fields"]["wind_speed"]["value"]
                data_cache.cached_fields["wind_speed"] = True
                any_field_using_cache = True
                
                cached_time = data_cache.last_valid_data["fields"]["wind_speed"]["timestamp"]
                age_str = format_age_string(current_time, cached_time)
                
                logger.info(f"Using cached wind speed data: {latest_weather['wind_speed']} mph from {cached_time.isoformat()} ({age_str} old)")
                
                # Store info about this cached field
                cached_fields_info.append({
                    "field": "wind_speed",
                    "value": latest_weather["wind_speed"],
                    "timestamp": cached_time,
                    "age": age_str
                })
            
            if latest_weather["soil_moisture_15cm"] is None and data_cache.last_valid_data["fields"]["soil_moisture"]["value"] is not None:
                latest_weather["soil_moisture_15cm"] = data_cache.last_valid_data["fields"]["soil_moisture"]["value"]
                data_cache.cached_fields["soil_moisture"] = True
                any_field_using_cache = True
                
                cached_time = data_cache.last_valid_data["fields"]["soil_moisture"]["timestamp"]
                age_str = format_age_string(current_time, cached_time)
                
                logger.info(f"Using cached soil moisture data: {latest_weather['soil_moisture_15cm']}% from {cached_time.isoformat()} ({age_str} old)")
                
                # Store info about this cached field
                cached_fields_info.append({
                    "field": "soil_moisture",
                    "value": latest_weather["soil_moisture_15cm"],
                    "timestamp": cached_time,
                    "age": age_str
                })
            
            if latest_weather["wind_gust"] is None and data_cache.last_valid_data["fields"]["wind_gust"]["value"] is not None:
                latest_weather["wind_gust"] = data_cache.last_valid_data["fields"]["wind_gust"]["value"]
                data_cache.cached_fields["wind_gust"] = True
                any_field_using_cache = True
                
                cached_time = data_cache.last_valid_data["fields"]["wind_gust"]["timestamp"]
                age_str = format_age_string(current_time, cached_time)
                
                logger.info(f"Using cached wind gust data: {latest_weather['wind_gust']} mph from {cached_time.isoformat()} ({age_str} old)")
                
                # Store info about this cached field
                cached_fields_info.append({
                    "field": "wind_gust",
                    "value": latest_weather["wind_gust"],
                    "timestamp": cached_time,
                    "age": age_str
                })
            
            # Update the global cache flag if any fields are using cached data
            data_cache.using_cached_data = any_field_using_cache
            
            # If all individual fields are missing and we have no cache for them, that's a problem
            if (latest_weather["air_temp"] is None and 
                latest_weather["relative_humidity"] is None and 
                latest_weather["wind_speed"] is None and 
                latest_weather["soil_moisture_15cm"] is None and 
                latest_weather["wind_gust"] is None):
                
                logger.warning("All critical data fields are missing")
                
                # If we have valid cached data, use it as a fallback
                if data_cache.last_valid_data["timestamp"] is not None:
                    logger.info(f"Falling back to cached data from {data_cache.last_valid_data['timestamp']}")
                    
                    # Mark that we're using cached data
                    data_cache.using_cached_data = True
                    
                    # Use the cached data but update the timestamps to reflect this is old data
                    cached_weather_data = data_cache.last_valid_data["synoptic_data"]
                    cached_wunderground_data = data_cache.last_valid_data["wunderground_data"]
                    cached_fire_risk_data = data_cache.last_valid_data["fire_risk_data"].copy()
                    
                    # Update the cache with the cached data (this will update timestamps)
                    current_time = datetime.now(TIMEZONE)
                    
                    # Calculate how old the data is for display
                    cached_time = data_cache.last_valid_data["timestamp"]
                    age_str = format_age_string(current_time, cached_time)
                    
                    # Update the cached data to indicate it's not current
                    cached_fire_risk_data["cached_data"] = {
                        "is_cached": True,
                        "original_timestamp": cached_time.isoformat(),
                        "age": age_str
                    }
                    
                    # Update cache with the cached data but new timestamp
                    with data_cache._lock:
                        data_cache.synoptic_data = cached_weather_data
                        data_cache.wunderground_data = cached_wunderground_data
                        data_cache.fire_risk_data = cached_fire_risk_data
                        data_cache.last_updated = current_time
                        data_cache.last_update_success = False
                        
                        # Signal update completion even though we're using cached data
                        try:
                            loop = asyncio.get_event_loop()
                            if not loop.is_closed():
                                loop.call_soon_threadsafe(data_cache._update_complete_event.set)
                        except Exception as e:
                            logger.error(f"Error signaling update completion: {e}")
                    
                    # Log the fallback
                    logger.info(f"Using cached data from {cached_time.isoformat()} as fallback")
                    success = True
                    return True
                else:
                    # No cached data available either
                    raise ValueError("All critical data sources failed and no cached data available")
            
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

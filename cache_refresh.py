import asyncio
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from fastapi import BackgroundTasks

from config import TIMEZONE, logger
from api_clients import get_synoptic_data
from tests.mock_utils import get_wunderground_data
from data_processing import combine_weather_data, format_age_string
from fire_risk_logic import calculate_fire_risk
from cache import data_cache
from email_service import send_test_email # Import the email sending function

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
        """Fetch weather data using asyncio."""
        loop = asyncio.get_running_loop()
        
        # Define function to run in thread pool
        def fetch_synoptic():
            return get_synoptic_data()
        
        # Run API call in thread pool
        try:
            weather_data_task = loop.run_in_executor(None, fetch_synoptic)
            
            # Wait for task to complete with timeout
            weather_data = await weather_data_task
            
            # Check for exceptions
            if isinstance(weather_data, Exception):
                logger.error(f"Error fetching Synoptic data: {weather_data}")
                weather_data = None
                
            return weather_data
                
        except Exception as e:
            logger.error(f"Error during concurrent data fetch: {e}")
            return None, None
    
    while not success and retries < data_cache.max_retries:
        try:
            # Check if we're exceeding our total timeout
            if time.time() - start_time > data_cache.update_timeout:
                logger.warning(f"Data refresh taking too long (over {data_cache.update_timeout}s), aborting")
                break
                
            # Fetch data from Synoptic API
            weather_data = await fetch_all_data()
            
            # Initialize variables for tracking cached data usage
            any_field_using_cache = False
            cached_fields_info = []
            
            # Process the API response to get the latest weather data
            latest_weather = combine_weather_data(weather_data, data_cache.cached_fields)
            
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
            
            # Get the previous risk level before calculating the new one
            previous_risk = data_cache.previous_risk_level
            
            # Calculate fire risk based on the latest weather data
            risk, explanation = calculate_fire_risk(latest_weather)
            
            # --- Email Alert Logic ---
            if previous_risk == "Orange" and risk == "Red":
                logger.info(f"Risk transition detected: {previous_risk} -> {risk}. Sending alert.")
                try:
                    # Construct email content
                    subject = "Fire Risk Alert: Level Increased to RED"
                    body = (
                        f"The fire risk level for Sierra City has increased from Orange to RED.\n\n"
                        f"Reason: {explanation}\n\n"
                        f"Current Conditions:\n"
                        f"- Temperature: {latest_weather.get('air_temp', 'N/A')}°C\n"
                        f"- Humidity: {latest_weather.get('relative_humidity', 'N/A')}%\n"
                        f"- Wind Speed: {latest_weather.get('wind_speed', 'N/A')} mph\n"
                        f"- Wind Gusts: {latest_weather.get('wind_gust', 'N/A')} mph\n"
                        f"- Soil Moisture (15cm): {latest_weather.get('soil_moisture_15cm', 'N/A')}%\n\n"
                        f"Please consult the dashboard for full details and safety recommendations."
                    )
                    
                    # Send the email
                    send_test_email(
                        sender="advisory@scfireweather.org",
                        recipient="info@scfireweather.org", # Use the confirmed recipient
                        subject=subject,
                        body_text=body
                    )
                    logger.info("Orange-to-Red alert email sent successfully.")
                except Exception as email_err:
                    logger.error(f"Failed to send Orange-to-Red alert email: {email_err}")
            # --- End Email Alert Logic ---

            # Update the previous risk level in the cache *after* checking the transition
            data_cache.previous_risk_level = risk
            
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
            
            # Check if we got any fresh data from API
            # If it's None, the refresh essentially failed to get new data
            if weather_data is None:
                 logger.warning("Synoptic API call failed, refresh did not obtain new data.")
                 # Keep success as False if it wasn't already True from a previous retry
                 # success = False # This line is implicitly handled by loop condition
            else:
                 # Update cache with new data
                 data_cache.update_cache(weather_data, fire_risk_data)
                 # If we got here with some data, the refresh was successful in processing
                 success = True
                 logger.info("Data cache refresh successful (processed available data)")

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
        
        # When refresh fails completely, ensure we're explicitly set to use cached data
        data_cache.using_cached_data = True
        
        # Make sure all fields are marked as using cached data
        for field in data_cache.cached_fields:
            data_cache.cached_fields[field] = True
        
        # Get the cached data to update with correct cache markers
        if data_cache.fire_risk_data:
            # Make a copy of the existing fire risk data
            fire_risk_data = data_cache.fire_risk_data.copy()
            
            # Ensure cached_data object is present and properly formatted
            current_time = datetime.now(TIMEZONE)
            cached_time = data_cache.last_valid_data["timestamp"]
            
            # Calculate age of data
            age_str = format_age_string(current_time, cached_time)
            
            # Add or update cached_data field in fire_risk_data
            fire_risk_data["cached_data"] = {
                "is_cached": True,
                "original_timestamp": cached_time.isoformat(),
                "age": age_str,
                "cached_fields": data_cache.cached_fields.copy()
            }
            
            # Make sure weather data has the cached_fields structure
            if "weather" in fire_risk_data:
                if "cached_fields" not in fire_risk_data["weather"]:
                    fire_risk_data["weather"]["cached_fields"] = {}
                
                # Copy the cached_fields structure with all fields marked as cached
                fire_risk_data["weather"]["cached_fields"] = data_cache.cached_fields.copy()
                
                # Add timestamp information for each field
                if "timestamp" not in fire_risk_data["weather"]["cached_fields"]:
                    fire_risk_data["weather"]["cached_fields"]["timestamp"] = {}
                
                for field_name in data_cache.cached_fields:
                    if field_name in data_cache.last_valid_data["fields"]:
                        field_timestamp = data_cache.last_valid_data["fields"][field_name].get("timestamp")
                        if field_timestamp:
                            fire_risk_data["weather"]["cached_fields"]["timestamp"][field_name] = field_timestamp.isoformat()
                
                # Add modal content to indicate cached data
                fire_risk_data["modal_content"] = {
                    "note": "Displaying cached weather data. Current data is unavailable.",
                    "warning_title": "Using Cached Data",
                    "warning_issues": ["Unable to fetch fresh data from weather APIs."]
                }
            
            # Update the cache with the properly marked data
            data_cache.fire_risk_data = fire_risk_data
        
        logger.info("Fallback to cached data after refresh failure with proper cache indicators")
    
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

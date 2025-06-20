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
# Import admin_sessions to check type, though not strictly necessary for Optional[Dict]
# from admin_endpoints import admin_sessions # Not needed if we just pass it as Dict
# Import the specific alert function and subscriber function
from email_service import send_orange_to_red_alert
from subscriber_service import get_active_subscribers

async def refresh_data_cache(
    background_tasks: Optional[BackgroundTasks] = None, 
    force: bool = False,
    session_token: Optional[str] = None,            # New parameter
    current_admin_sessions: Optional[Dict] = None   # New parameter
) -> bool:
    """Refresh the data cache by fetching new data from APIs.
    
    Args:
        background_tasks: Optional BackgroundTasks for scheduling future refreshes.
        force: Force refresh even if an update is already in progress.
        session_token: Optional admin session token.
        current_admin_sessions: Optional dictionary of current admin sessions.
    
    Returns:
        bool: True if refresh was successful, False otherwise.
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
    logger.info(f"Cached fields state at refresh start: {data_cache.cached_fields}")
    
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
            
            # Calculate fire risk based on the latest weather data
            manual_overrides = None
            logger.info(f"Cache Refresh: Checking for admin overrides. session_token received: {session_token[:8] if session_token else 'None'}")
            if current_admin_sessions:
                logger.info(f"Cache Refresh: current_admin_sessions keys: {list(current_admin_sessions.keys())}")
            else:
                logger.info("Cache Refresh: current_admin_sessions is None or empty.")

            if session_token and current_admin_sessions and session_token in current_admin_sessions:
                logger.info(f"Cache Refresh: session_token '{session_token[:8]}...' FOUND in current_admin_sessions.")
                admin_session_data = current_admin_sessions[session_token]
                manual_overrides = admin_session_data.get('manual_weather_overrides')
                if manual_overrides:
                    logger.info(f"Cache Refresh: Applying admin overrides for session {session_token[:8]}...: {manual_overrides}")
                else:
                    logger.info(f"Cache Refresh: No 'manual_weather_overrides' found in session data for token {session_token[:8]}...")
            elif session_token:
                logger.info(f"Cache Refresh: session_token '{session_token[:8]}...' NOT FOUND in current_admin_sessions or current_admin_sessions is None.")
            else:
                logger.info("Cache Refresh: No session_token provided, not checking for admin overrides.")
            
            # Capture all three return values: risk, explanation, and effective_weather_values
            risk, explanation, effective_eval_data = calculate_fire_risk(latest_weather, manual_overrides=manual_overrides)

            # Update latest_weather with effective values when admin overrides are active
            if manual_overrides and effective_eval_data:
                logger.info(f"🔧 Applying admin overrides to weather data for frontend display")
                
                # Map effective_eval_data back to latest_weather format
                if effective_eval_data.get('temperature') is not None:
                    # Convert temperature from Fahrenheit back to Celsius for storage
                    temp_f = effective_eval_data['temperature']
                    latest_weather['air_temp'] = (temp_f - 32) * 5/9
                    logger.info(f"🔧 Override temperature: {temp_f}°F -> {latest_weather['air_temp']:.2f}°C")
                
                if effective_eval_data.get('humidity') is not None:
                    latest_weather['relative_humidity'] = effective_eval_data['humidity']
                    logger.info(f"🔧 Override humidity: {effective_eval_data['humidity']}%")
                
                if effective_eval_data.get('wind_speed') is not None:
                    # Convert mph back to m/s for storage (frontend will convert back to mph for display)
                    wind_speed_ms = effective_eval_data['wind_speed'] / 2.237
                    latest_weather['wind_speed'] = wind_speed_ms
                    logger.info(f"🔧 Override wind speed: {effective_eval_data['wind_speed']} mph -> {wind_speed_ms:.2f} m/s")
                
                if effective_eval_data.get('wind_gust') is not None:
                    # Convert mph back to m/s for storage (frontend will convert back to mph for display)
                    wind_gust_ms = effective_eval_data['wind_gust'] / 2.237
                    latest_weather['wind_gust'] = wind_gust_ms
                    logger.info(f"🔧 Override wind gust: {effective_eval_data['wind_gust']} mph -> {wind_gust_ms:.2f} m/s")
                
                if effective_eval_data.get('soil_moisture') is not None:
                    latest_weather['soil_moisture_15cm'] = effective_eval_data['soil_moisture']
                    logger.info(f"🔧 Override soil moisture: {effective_eval_data['soil_moisture']}%")

            # Determine if daily email limit should be ignored for this admin
            ignore_email_daily_limit_pref = False
            if session_token and current_admin_sessions and session_token in current_admin_sessions:
                admin_session_data = current_admin_sessions[session_token]
                ignore_email_daily_limit_pref = admin_session_data.get('ignore_email_daily_limit', False)
                if ignore_email_daily_limit_pref:
                    logger.info(f"Admin session {session_token[:8]}... has 'ignore_email_daily_limit' set to True.")
            
            # --- Wind Data Check ---
            # Log wind data state to diagnose refresh issues
            wind_gust_value = latest_weather.get('wind_gust')
            logger.info(f"⚡ Wind gust value from API/processing: {wind_gust_value} (None means missing)")
            
            # Check the wind_gust data station by station
            if 'wind_gust_stations' in latest_weather:
                logger.info(f"⚡ Number of wind gust stations: {len(latest_weather['wind_gust_stations'])}")
                for station_id, station_data in latest_weather['wind_gust_stations'].items():
                    logger.info(f"⚡ Station {station_id}: value={station_data.get('value')}, cached={station_data.get('is_cached', False)}")
            else:
                logger.info("⚡ No wind gust station data available")
            
            # Verify wind data is properly refreshed
            if data_cache.cached_fields["wind_speed"] or data_cache.cached_fields["wind_gust"]:
                logger.warning("⚠️ Wind data marked as cached after processing new data - manually fixing!")
                
                # Before resetting, log the state of the latest weather data
                logger.info(f"⚡ Before reset - wind_speed={latest_weather.get('wind_speed')}, wind_gust={latest_weather.get('wind_gust')}")
                
                # Reset the wind cached flags to ensure data refreshes properly
                data_cache.cached_fields["wind_speed"] = False
                data_cache.cached_fields["wind_gust"] = False
                logger.info("⚡ Reset wind data cached flags to ensure fresh data")
                
                # Force wind data to show as fresh in latest_weather
                if latest_weather.get('wind_gust') is None and 'wind_gust' in data_cache.last_valid_data["fields"]:
                    # If wind_gust is None in latest_weather but we have a cached value, use the cached value 
                    # but mark it as NOT cached (this is a workaround for the refresh issue)
                    cached_value = data_cache.last_valid_data["fields"]["wind_gust"]["value"]
                    logger.info(f"⚡ Manually injecting wind_gust value {cached_value} from cache but marking as fresh")
                    latest_weather['wind_gust'] = cached_value
            
            # --- Email Alert Logic ---
            email_alert_triggered_this_cycle = False
            
            # DETAILED LOGGING FOR EMAIL ALERT BUG DIAGNOSIS
            logger.info(f"🚨 EMAIL ALERT LOGIC DEBUG:")
            logger.info(f"🚨 Current risk level: {risk}")
            logger.info(f"🚨 Previous risk level: {data_cache.previous_risk_level}")
            logger.info(f"🚨 Risk level timestamp: {data_cache.risk_level_timestamp}")
            logger.info(f"🚨 Last alerted timestamp: {data_cache.last_alerted_timestamp}")
            logger.info(f"🚨 Ignore daily limit preference: {ignore_email_daily_limit_pref}")
            
            should_send_alert = data_cache.should_send_alert_for_transition(risk, ignore_daily_limit=ignore_email_daily_limit_pref)
            logger.info(f"🚨 should_send_alert_for_transition() returned: {should_send_alert}")
            
            # Check if we should send an alert for this risk level, considering the admin's preference
            if should_send_alert:
                email_alert_triggered_this_cycle = True # Mark that we entered the alert logic path
                logger.info(f"🚨 ENTERING EMAIL ALERT LOGIC!")
                logger.info(f"Risk transition detected: {data_cache.previous_risk_level} -> {risk}. Preparing alert. (ignore_daily_limit={ignore_email_daily_limit_pref})")
                try:
                    # 1. Get active subscribers
                    subscribers_result = get_active_subscribers()

                    # Check for error in subscribers result
                    if "error" in subscribers_result:
                        logger.error(f"Failed to get subscribers: {subscribers_result['error']}")
                        recipients = []
                        data_cache.last_email_send_outcome = "failed" # Failed to get subscribers
                    else:
                        recipients = subscribers_result.get("subscribers", [])

                    if not recipients:
                        logger.warning("Orange-to-Red transition detected, but no active subscribers found.")
                        if data_cache.last_email_send_outcome != "failed": # Don't overwrite a previous failure
                            data_cache.last_email_send_outcome = "not_triggered_no_recipients"
                    else:
                        logger.info(f"Found {len(recipients)} active subscribers for the alert.")
                        # 2. Prepare weather data using effective_eval_data for the email content
                        alert_weather_data = {
                            'temperature': f"{effective_eval_data.get('temperature', 'N/A')}°F", # Now using Fahrenheit
                            'humidity': f"{effective_eval_data.get('humidity', 'N/A')}%",
                            'wind_speed': f"{effective_eval_data.get('wind_speed', 'N/A')} mph",
                            'wind_gust': f"{effective_eval_data.get('wind_gust', 'N/A')} mph",
                            'soil_moisture': f"{effective_eval_data.get('soil_moisture', 'N/A')}%"
                        }

                        # 3. Send the alert using the dedicated function
                        message_id = send_orange_to_red_alert(recipients, alert_weather_data)

                        if message_id:
                            logger.info(f"Orange-to-Red alert email sent successfully to {len(recipients)} subscribers. Message ID: {message_id}")
                            data_cache.record_alert_sent()
                            data_cache.last_email_send_outcome = "success"
                        else:
                            logger.error("Failed to send Orange-to-Red alert email (send_orange_to_red_alert returned None).")
                            data_cache.last_email_send_outcome = "failed"

                except Exception as email_err:
                    logger.error(f"Failed during Orange-to-Red alert process: {email_err}", exc_info=True) # Log traceback
                    data_cache.last_email_send_outcome = "failed"
            else: # should_send_alert_for_transition was false
                if not email_alert_triggered_this_cycle: # Only set if we didn't even attempt to send
                    data_cache.last_email_send_outcome = "not_triggered_conditions_met"

            # --- End Email Alert Logic ---

            # Update the risk level in the cache with timestamp
            data_cache.update_risk_level(risk)
            
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
                
                # Explicitly set the update complete event after successful update
                try:
                    logger.info("✅ Explicitly setting update complete event after successful refresh")
                    data_cache._update_complete_event.set()
                except Exception as e:
                    logger.error(f"⚠️ Error explicitly setting update complete event: {e}")
                
                logger.info("✅ Data cache refresh successful (processed available data)")

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

        # Ensure fire_risk_data exists, even if minimal, to store cache status
        if not data_cache.fire_risk_data:
             # Initialize with a default/error state if completely empty
             logger.warning("Initializing fire_risk_data in cache during fallback as it was empty.")
             data_cache.fire_risk_data = {
                 "risk": "Unknown",
                 "explanation": "Failed to fetch initial data.",
                 "weather": {}, # Start with empty weather
                 "cached_data": {} # Initialize cached_data structure
             }

        # Now, we can safely assume data_cache.fire_risk_data is a dict
        # Make a copy to modify
        fire_risk_data = data_cache.fire_risk_data.copy()

        # Ensure essential keys exist before trying to access them
        fire_risk_data.setdefault("weather", {})
        fire_risk_data.setdefault("cached_data", {})
        fire_risk_data["weather"].setdefault("cached_fields", {})
        fire_risk_data["weather"]["cached_fields"].setdefault("timestamp", {})

        # Ensure cached_data object is present and properly formatted
        try:
            # Attempt to get the timestamp of the last known valid data
            current_time = datetime.now(TIMEZONE)
            # Use a sensible default if last_valid_data itself is missing
            cached_time = data_cache.last_valid_data.get("timestamp", current_time)
            age_str = format_age_string(current_time, cached_time)
            original_timestamp_iso = cached_time.isoformat()

            # Add or update cached_data field in fire_risk_data
            fire_risk_data["cached_data"].update({
                "is_cached": True,
                "original_timestamp": original_timestamp_iso,
                "age": age_str,
                "cached_fields": data_cache.cached_fields.copy() # Mark all as cached
            })

            # Ensure weather data reflects cached state
            fire_risk_data["weather"]["cached_fields"] = data_cache.cached_fields.copy()
            fire_risk_data["weather"]["cached_fields"]["timestamp"] = {} # Reset timestamps dict

            # Add timestamp information for each field if available in last_valid_data
            if data_cache.last_valid_data and "fields" in data_cache.last_valid_data:
                 for field_name in data_cache.cached_fields:
                     field_data = data_cache.last_valid_data["fields"].get(field_name, {})
                     field_timestamp = field_data.get("timestamp")
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

        except KeyError as e:
             logger.error(f"Fallback logic failed: Missing key {e} in data_cache.last_valid_data. Cache might be incomplete.", exc_info=True)
             # Ensure a minimal error state is still set in the cache
             data_cache.fire_risk_data = {
                 "risk": "Unknown",
                 "explanation": f"Failed to fetch data and process fallback due to missing key: {e}",
                 "weather": {},
                 "cached_data": {"is_cached": True, "cached_fields": data_cache.cached_fields.copy()}
             }
        except Exception as fallback_err:
            logger.error(f"Unexpected error during fallback logic: {fallback_err}", exc_info=True)
            # Ensure a minimal error state
            data_cache.fire_risk_data = {
                 "risk": "Unknown",
                 "explanation": f"Failed to fetch data and process fallback due to error: {fallback_err}",
                 "weather": {},
                 "cached_data": {"is_cached": True, "cached_fields": data_cache.cached_fields.copy()}
             }
        # End of the 'if not success' block's try/except

    # Schedule next refresh if running as a background task
    # This should be outside the 'if not success' block's try/except, but still within the main function scope
    if background_tasks and not data_cache.refresh_task_active:
        # Schedule the next refresh based on the configured interval
        # Pass along session_token and current_admin_sessions if they were provided to this refresh cycle
        # However, for a background scheduled task, it's unlikely/undesirable to persist a specific user's session overrides.
        # So, for scheduled tasks, we'll call refresh_data_cache without these specific user session overrides.
        # If a user is actively making a request that triggers a refresh, their overrides will be used for *that* refresh.
        background_tasks.add_task(schedule_next_refresh, data_cache.background_refresh_interval, None, None) # Pass None for session specific args
        data_cache.refresh_task_active = True

    return success

async def schedule_next_refresh(
    minutes: int, 
    session_token: Optional[str] = None, # Added for consistency, but likely None for scheduled
    current_admin_sessions: Optional[Dict] = None # Added for consistency, but likely None for scheduled
):
    """Schedule the next refresh after a delay."""
    try:
        logger.info(f"Scheduling next background refresh in {minutes} minutes")
        await asyncio.sleep(minutes * 60)
        # When calling refresh_data_cache for a scheduled task,
        # we typically don't want to apply a specific admin's overrides.
        # So, we call it without session_token and current_admin_sessions,
        # or explicitly pass None if the signature requires them.
        await refresh_data_cache(
            background_tasks=None, # No further background tasks to spawn from here in this model
            force=False, 
            session_token=session_token, # Will be None for typical scheduled calls
            current_admin_sessions=current_admin_sessions # Will be None for typical scheduled calls
        )
    except Exception as e:
        logger.error(f"Error in scheduled refresh: {e}")
    finally:
        # Reset the refresh task flag so we can schedule again
        data_cache.refresh_task_active = False

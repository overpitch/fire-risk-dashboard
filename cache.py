import threading
import asyncio
import time
import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import pytz
from pathlib import Path

from config import TIMEZONE, logger

class DataCache:
    # Default values for when no data is available
    # These are reasonable fallback values for Sierra City area
    DEFAULT_VALUES = {
        "temperature": 15.0,           # 59°F - mild temperature
        "humidity": 40.0,              # 40% - moderate humidity
        "wind_speed": 5.0,             # 5 mph - light breeze
        "soil_moisture": 20.0,         # 20% - moderately dry soil
        "wind_gust": 8.0               # 8 mph - light gusts
    }
    
    def __init__(self):
        self.synoptic_data: Optional[Dict[str, Any]] = None
        self.wunderground_data: Optional[Dict[str, Any]] = None
        self.fire_risk_data: Optional[Dict[str, Any]] = None
        self.previous_risk_level: Optional[str] = None # Added to track the last known risk level
        self.risk_level_timestamp: Optional[datetime] = None # When the risk level was last updated
        self.last_alerted_timestamp: Optional[datetime] = None # When the last alert was sent
        self.last_updated: Optional[datetime] = None
        self.update_in_progress: bool = False
        self.last_update_success: bool = False
        self.max_retries: int = 5  # Increased from 3 to 5
        self.retry_delay: int = 5  # seconds
        self.update_timeout: int = 30  # seconds - increased from 15s to give more time for refresh
        self.background_refresh_interval: int = 10  # minutes
        self.data_timeout_threshold: int = 30  # minutes - max age before data is considered too old
        self.refresh_task_active: bool = False
        self.last_email_send_outcome: Optional[str] = None # To track email sending status for UI feedback
        # Lock for thread safety
        self._lock = threading.Lock()
        # Event to signal when an update is complete
        self._update_complete_event = asyncio.Event()
        
        # Set up cache file path - store in data directory
        self.cache_dir = Path("data")
        self.cache_file = self.cache_dir / "weather_cache.json"
        
        # Initialize with current time
        current_time = datetime.now(TIMEZONE)
        
        # First try to load cache from disk
        disk_cache_loaded, disk_cache = self._load_cache_from_disk()
        
        if not disk_cache_loaded:
            # No disk cache available, initialize with default values
            logger.info("No disk cache found, initializing with default values")
            
            # Storage for last known valid data by field
            self.last_valid_data: Dict[str, Any] = {
                # Store each weather field individually with its own timestamp
                "fields": {
                    "temperature": {"value": self.DEFAULT_VALUES["temperature"], "timestamp": current_time},
                    "humidity": {"value": self.DEFAULT_VALUES["humidity"], "timestamp": current_time},
                    "wind_speed": {"value": self.DEFAULT_VALUES["wind_speed"], "timestamp": current_time},
                    "soil_moisture": {"value": self.DEFAULT_VALUES["soil_moisture"], "timestamp": current_time},
                    "wind_gust": {
                        "value": self.DEFAULT_VALUES["wind_gust"],  # Average value for backward compatibility
                        "timestamp": current_time,
                        "stations": {
                            # Store per-station data
                            # Each station will have {"value": float, "timestamp": datetime}
                        }
                    }
                },
                # Keep the whole API responses for backwards compatibility
                "synoptic_data": None,
                "wunderground_data": None,
                "fire_risk_data": None,
                "timestamp": current_time,
            }
            # Initialize cache fields flags - mark as NOT cached to force API data fetch
            self.cached_fields: Dict[str, bool] = {
                "temperature": False,  # Initialize without using cached data
                "humidity": False,
                "wind_speed": False,
                "soil_moisture": False,
                "wind_gust": False
            }
            # IMPORTANT: Set to FALSE by default - do not start in test mode
            self.using_cached_data: bool = False  # Start in normal mode, not test mode
            self.using_default_values: bool = True  # Still track that we're using defaults
            
            logger.info("⚠️ New deployment detected - starting in NORMAL mode (not test mode)")
        else:
            # Disk cache was loaded successfully, cached_fields and using_cached_data 
            # will be already set by _load_cache_from_disk
            self.using_default_values = False
            # Also load previous risk level if available
            if "previous_risk_level" in disk_cache:
                self.previous_risk_level = disk_cache["previous_risk_level"]

    def is_stale(self, max_age_minutes: int = 15) -> bool:
        """Check if the data is stale (older than max_age_minutes)"""
        if self.last_updated is None:
            return True
        # Use timezone-aware comparison
        now = datetime.now(TIMEZONE)
        age = now - self.last_updated
        return age > timedelta(minutes=max_age_minutes)
    
    def is_critically_stale(self) -> bool:
        """Check if the data is critically stale (older than data_timeout_threshold)"""
        if self.last_updated is None:
            return True
        # Use timezone-aware comparison
        now = datetime.now(TIMEZONE)
        age = now - self.last_updated
        return age > timedelta(minutes=self.data_timeout_threshold)
    
    def update_cache(self, synoptic_data, fire_risk_data):
        """Update the cache with new data"""
        # Create timezone-aware datetime for Pacific timezone
        current_time = datetime.now(TIMEZONE)
        
        # Save the current cached fields state before updating
        cached_fields_state = self.cached_fields.copy()
        using_cached_data_state = self.using_cached_data
        
        with self._lock:
            self.synoptic_data = synoptic_data
            self.wunderground_data = None  # No longer used
            
            # If we're using cached data, make sure the fire_risk_data has a cached_data field
            # Use self.using_cached_data directly now
            if self.using_cached_data and "cached_data" not in fire_risk_data: # Use self.using_cached_data
                # Get timestamp information for display
                cached_time = self.last_valid_data["timestamp"]
                if cached_time:
                    # Calculate age of data
                    age_delta = current_time - cached_time
                    if age_delta.days > 0:
                        age_str = f"{age_delta.days} day{'s' if age_delta.days != 1 else ''}"
                    elif age_delta.seconds // 3600 > 0:
                        hours = age_delta.seconds // 3600
                        age_str = f"{hours} hour{'s' if hours != 1 else ''}"
                    else:
                        minutes = age_delta.seconds // 60
                        age_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
                    
                    # Add cached_data field to fire_risk_data
                    fire_risk_data["cached_data"] = {
                        "is_cached": True,
                        "original_timestamp": cached_time.isoformat(),
                        "age": age_str,
                        "cached_fields": self.cached_fields.copy() # Use self.cached_fields directly
                    }
            
            self.fire_risk_data = fire_risk_data
            self.last_updated = current_time
            self.last_update_success = True
            
            # MODIFIED CACHE STATE HANDLING:
            # First, check wind data - ensure it's correctly marked as cached/non-cached
            if "weather" in fire_risk_data:
                weather = fire_risk_data.get("weather", {})
                
                # Check if wind_speed is present in the fresh data
                if weather.get("wind_speed") is not None:
                    cached_fields_state["wind_speed"] = False
                else:
                    # If wind_speed is None, it should be marked as cached
                    cached_fields_state["wind_speed"] = True
                    
                # Check if wind_gust is present in the fresh data
                if weather.get("wind_gust") is not None:
                    # Check if the wind_gust is actually from cache
                    wind_gust_stations = weather.get("wind_gust_stations", {})
                    for station in wind_gust_stations.values():
                        if station.get("is_cached", False):
                            cached_fields_state["wind_gust"] = True
                            break
                    else:
                        # If no station is cached, mark as not cached
                        cached_fields_state["wind_gust"] = False
                else:
                    # If wind_gust is None, it should be marked as cached
                    cached_fields_state["wind_gust"] = True
            
            # Now restore the cached_fields and using_cached_data state
            self.cached_fields = cached_fields_state
            # Recalculate using_cached_data based on actual field states
            self.using_cached_data = any(self.cached_fields.values())
            
            # Log cache state for monitoring
            logger.info(f"Cache state after update: using_cached_data={self.using_cached_data}")
            logger.info(f"Cached fields: {', '.join([f for f, v in self.cached_fields.items() if v])}")
            
            # Store the full response data for backwards compatibility
            # Always update timestamp and store the current values (even when they are None)
            # This ensures last_valid_data is always updated consistently
            self.last_valid_data["synoptic_data"] = synoptic_data
            self.last_valid_data["wunderground_data"] = None  # No longer used
            self.last_valid_data["fire_risk_data"] = fire_risk_data
            self.last_valid_data["timestamp"] = current_time
            
            # Only update individual field values if the data is available
            if synoptic_data is not None:
                
                # Update individual field values if they're available in the current data
                if fire_risk_data and "weather" in fire_risk_data:
                    weather = fire_risk_data["weather"]
                    
                    # Store each field individually if it has a valid value
                    if weather.get("air_temp") is not None:
                        self.last_valid_data["fields"]["temperature"]["value"] = weather["air_temp"]
                        self.last_valid_data["fields"]["temperature"]["timestamp"] = current_time
                    
                    if weather.get("relative_humidity") is not None:
                        self.last_valid_data["fields"]["humidity"]["value"] = weather["relative_humidity"]
                        self.last_valid_data["fields"]["humidity"]["timestamp"] = current_time
                    
                    if weather.get("wind_speed") is not None:
                        self.last_valid_data["fields"]["wind_speed"]["value"] = weather["wind_speed"]
                        self.last_valid_data["fields"]["wind_speed"]["timestamp"] = current_time
                    
                    if weather.get("soil_moisture_15cm") is not None:
                        self.last_valid_data["fields"]["soil_moisture"]["value"] = weather["soil_moisture_15cm"]
                        self.last_valid_data["fields"]["soil_moisture"]["timestamp"] = current_time
                    
                    # Store wind gust data - both the average and per-station values
                    if weather.get("wind_gust") is not None:
                        # Store the average value for backward compatibility
                        self.last_valid_data["fields"]["wind_gust"]["value"] = weather["wind_gust"]
                        self.last_valid_data["fields"]["wind_gust"]["timestamp"] = current_time
                        
                        # Store per-station data if available
                        if weather.get("wind_gust_stations"):
                            for station_id, station_data in weather["wind_gust_stations"].items():
                                # Initialize the station entry if it doesn't exist
                                if station_id not in self.last_valid_data["fields"]["wind_gust"]["stations"]:
                                    self.last_valid_data["fields"]["wind_gust"]["stations"][station_id] = {}
                                
                                # Only update if this is fresh data (not cached)
                                if not station_data.get("is_cached", False) and station_data.get("value") is not None:
                                    self.last_valid_data["fields"]["wind_gust"]["stations"][station_id] = {
                                        "value": station_data["value"],
                                        "timestamp": station_data.get("timestamp", current_time)
                                    }
                                    logger.info(f"Cached wind gust data for station {station_id}: {station_data['value']} mph")
                
                logger.info(f"Stored valid data for future fallback use at {current_time}")
            
            # Signal that the update is complete by setting the event
            try:
                logger.info("✅ Setting update_complete_event to signal refresh completion")
                
                # Try to get the current event loop
                try:
                    loop = asyncio.get_event_loop()
                    if not loop.is_closed():
                        logger.info("✅ Using call_soon_threadsafe to set event")
                        loop.call_soon_threadsafe(self._update_complete_event.set)
                    else:
                        logger.warning("⚠️ Loop is closed, setting event directly")
                        self._update_complete_event.set()
                except RuntimeError:
                    # If there's no event loop, set the event directly
                    logger.warning("⚠️ No event loop, setting event directly")
                    self._update_complete_event.set()
            except Exception as e:
                logger.error(f"⚠️ Error signaling update completion: {e}")
                # Last resort attempt to set the event
                try:
                    self._update_complete_event.set()
                    logger.info("✅ Set event directly after error")
                except Exception as e2:
                    logger.error(f"⚠️ Failed even direct event setting: {e2}")
        
        # Log cache update
        logger.info(f"Cache updated at {self.last_updated}")
        
        # Save cache to disk
        self._save_cache_to_disk()

    def get_and_clear_last_email_send_outcome(self) -> Optional[str]:
        """Returns the last email send outcome and then clears it."""
        with self._lock:
            outcome = self.last_email_send_outcome
            self.last_email_send_outcome = None
            return outcome
    
    def _load_cache_from_disk(self) -> tuple[bool, Dict[str, Any]]:
        """Load cached data from disk if available.
        
        Returns:
            bool: True if data was loaded successfully, False otherwise
        """
        try:
            if not self.cache_file.exists():
                logger.info(f"Cache file does not exist: {self.cache_file}")
                return False, {}
                
            with open(self.cache_file, 'r') as f:
                disk_cache = json.load(f)
                
            # Validate the loaded data
            if not disk_cache or "last_valid_data" not in disk_cache:
                logger.warning(f"Invalid cache file format: {self.cache_file}")
                return False, {}
                
            # Convert ISO timestamps back to datetime objects
            self._convert_timestamps(disk_cache["last_valid_data"])
            
            # Update cache with disk data
            self.last_valid_data = disk_cache["last_valid_data"]
            
            if "last_updated" in disk_cache and disk_cache["last_updated"]:
                self.last_updated = datetime.fromisoformat(disk_cache["last_updated"])
            
            # Load risk level and alert timestamps if available
            if "risk_level_timestamp" in disk_cache and disk_cache["risk_level_timestamp"]:
                self.risk_level_timestamp = datetime.fromisoformat(disk_cache["risk_level_timestamp"])
            
            if "last_alerted_timestamp" in disk_cache and disk_cache["last_alerted_timestamp"]:
                self.last_alerted_timestamp = datetime.fromisoformat(disk_cache["last_alerted_timestamp"])
            
            # Always initialize in normal mode, regardless of disk cache state
            # This ensures the system doesn't start in test mode by default
            self.cached_fields = {field: False for field in ["temperature", "humidity", "wind_speed", "soil_moisture", "wind_gust"]}
            self.using_cached_data = False  # ALWAYS start in normal mode
            
            # Log startup state
            has_valid_data = False
            if "fields" in self.last_valid_data:
                for field in ["temperature", "humidity", "wind_speed", "soil_moisture", "wind_gust"]:
                    if (field in self.last_valid_data["fields"] and 
                        self.last_valid_data["fields"][field].get("value") is not None):
                        has_valid_data = True
                        break
            
            if has_valid_data:
                logger.info("Valid data found in disk cache, but still starting in NORMAL mode")
            else:
                logger.info("No valid data in disk cache, starting in NORMAL mode with default values")
            
            logger.info(f"Successfully loaded cache from disk: {self.cache_file}")
            return True, disk_cache
        except Exception as e:
            logger.error(f"Error loading cache from disk: {e}")
            return False, {}
    
    def _save_cache_to_disk(self) -> bool:
        """Save current cache data to disk.
        
        Returns:
            bool: True if data was saved successfully, False otherwise
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(self.cache_dir, exist_ok=True)
            
            # Prepare data for serialization
            cache_data = {
                "last_valid_data": self._prepare_for_serialization(self.last_valid_data.copy()),
                "last_updated": self.last_updated.isoformat() if self.last_updated else None,
                "previous_risk_level": self.previous_risk_level, # Save the previous risk level
                "risk_level_timestamp": self.risk_level_timestamp.isoformat() if self.risk_level_timestamp else None,
                "last_alerted_timestamp": self.last_alerted_timestamp.isoformat() if self.last_alerted_timestamp else None
            }
            
            # Write to disk
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
                
            logger.info(f"Cache saved to disk: {self.cache_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving cache to disk: {e}")
            return False
            
    def _convert_timestamps(self, data: Dict[str, Any]) -> None:
        """Convert ISO timestamp strings back to datetime objects recursively."""
        if not data:
            return
            
        # Handle fields dictionary
        if "fields" in data:
            for field_name, field_data in data["fields"].items():
                if isinstance(field_data, dict):
                    if "timestamp" in field_data and field_data["timestamp"]:
                        try:
                            field_data["timestamp"] = datetime.fromisoformat(field_data["timestamp"])
                        except (ValueError, TypeError):
                            field_data["timestamp"] = datetime.now(TIMEZONE)
                    
                    # Handle wind_gust stations
                    if field_name == "wind_gust" and "stations" in field_data:
                        for station_id, station_data in field_data["stations"].items():
                            if "timestamp" in station_data and station_data["timestamp"]:
                                try:
                                    station_data["timestamp"] = datetime.fromisoformat(station_data["timestamp"])
                                except (ValueError, TypeError):
                                    station_data["timestamp"] = datetime.now(TIMEZONE)
        
        # Handle timestamp at the root level
        if "timestamp" in data and data["timestamp"]:
            try:
                data["timestamp"] = datetime.fromisoformat(data["timestamp"])
            except (ValueError, TypeError):
                data["timestamp"] = datetime.now(TIMEZONE)
    
    def _prepare_for_serialization(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert datetime objects to ISO strings for JSON serialization recursively."""
        if not data:
            return data
            
        # Deep copy to avoid modifying the original
        result = {}
        
        for key, value in data.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, dict):
                result[key] = self._prepare_for_serialization(value)
            else:
                result[key] = value
                
        return result
    
    def reset_update_event(self):
        """Reset the update complete event for next update cycle"""
        try:
            # FIXED: Issue 4.1 - Events not being properly reset
            # Previous implementation was double-clearing the event (direct + threadsafe)
            # Now we prioritize the threadsafe approach when a loop is active
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                loop.call_soon_threadsafe(self._update_complete_event.clear)
            else:
                # Direct approach only if no active loop
                self._update_complete_event.clear()
        except Exception as e:
            # Fallback to direct clearing if we can't get a loop
            self._update_complete_event.clear()
            logger.error(f"Error resetting update event: {e}")
    
    async def wait_for_update(self, timeout=None):
        """Wait for the current update to complete, with an optional timeout"""
        if timeout is None:
            timeout = self.update_timeout
        
        # Verify the event is properly initialized
        if self._update_complete_event is None:
            logger.error("⚠️ Update event is None, creating a new one")
            self._update_complete_event = asyncio.Event()
        
        logger.info(f"⏱️ Waiting for update to complete with timeout of {timeout}s...")
        
        # Check if the event is already set (meaning update is already complete)
        if self._update_complete_event.is_set():
            logger.info("✅ Update event was already set, returning immediately")
            return True
            
        try:
            # Wait for the event to be set with a timeout
            await asyncio.wait_for(self._update_complete_event.wait(), timeout=timeout)
            logger.info("✅ Update completed successfully within timeout")
            return True
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Timeout waiting for data update after {timeout} seconds")
            
            # Log the current cache state to help diagnose the issue
            logger.warning(f"⚠️ Current cached_fields state: {self.cached_fields}")
            logger.warning(f"⚠️ Update in progress: {self.update_in_progress}")
            
            # Check cache age to see if data is critically stale
            if self.last_updated:
                age_minutes = (datetime.now(TIMEZONE) - self.last_updated).total_seconds() / 60
                logger.warning(f"⚠️ Cache age: {age_minutes:.1f} minutes")
            
            return False
    
    def get_field_value(self, field_name: str, use_default_if_missing: bool = False) -> Any:
        """Get a value for a field, with fallbacks to ensure we never return None
        
        Args:
            field_name: The internal field name (temperature, humidity, etc.)
            use_default_if_missing: If True, use default values instead of cached values when direct values are not available
            
        Returns:
            The field value, guaranteed to never be None
        """
        # Map from internal field name to API response field name
        field_mapping = {
            "temperature": "air_temp",
            "humidity": "relative_humidity",
            "wind_speed": "wind_speed",
            "soil_moisture": "soil_moisture_15cm",
            "wind_gust": "wind_gust"
        }
        
        response_field_name = field_mapping.get(field_name)
        
        # First try to get the value from the current fire_risk_data
        if (self.fire_risk_data and 
            "weather" in self.fire_risk_data and 
            response_field_name in self.fire_risk_data["weather"] and
            self.fire_risk_data["weather"][response_field_name] is not None):
            
            # Check if the value is from cache (for wind_gust specifically)
            is_cached = False
            if field_name == "wind_gust" and "wind_gust_stations" in self.fire_risk_data["weather"]:
                # Check if any station has cached data
                for station_data in self.fire_risk_data["weather"]["wind_gust_stations"].values():
                    if station_data.get("is_cached", False):
                        is_cached = True
                        break
            
            # Only update the cached flag if it's not a cached value
            if not is_cached:
                # Reset cached flag for this field since we're using direct value
                self.cached_fields[field_name] = False
                
                # Check if any field is still using cached data
                self.using_cached_data = any(self.cached_fields.values())
            
            return self.fire_risk_data["weather"][response_field_name]
        
        # If use_default_if_missing is True, skip the cached data and go straight to defaults
        # This is useful during tests to ensure consistent behavior
        if not use_default_if_missing:
            # Try to get the value from last_valid_data.fields
            if (self.last_valid_data and 
                "fields" in self.last_valid_data and 
                field_name in self.last_valid_data["fields"] and
                self.last_valid_data["fields"][field_name].get("value") is not None):
                
                # Mark that we're using cached data for this field
                self.cached_fields[field_name] = True
                self.using_cached_data = True
                
                return self.last_valid_data["fields"][field_name]["value"]
        
        # Final fallback - use default value
        logger.warning(f"No data available for {field_name}, using default value")
        self.cached_fields[field_name] = True
        self.using_cached_data = True
        
        return self.DEFAULT_VALUES[field_name]
    
    def should_send_alert_for_transition(self, current_risk: str, ignore_daily_limit: bool = False) -> bool:
        """Determine if an alert should be sent based on current and previous risk levels.
        
        This method handles the case where a transition may have occurred during server downtime.
        It also limits alerts to once per calendar day, unless ignore_daily_limit is True.
        
        Args:
            current_risk: The current risk level ("Red" or "Orange").
            ignore_daily_limit: If True, bypass the once-per-day check.
            
        Returns:
            bool: True if an alert should be sent, False otherwise.
        """
        current_time = datetime.now(TIMEZONE)
        
        # No alert needed if current risk is not Red
        if current_risk != "Red":
            return False
            
        # No alert needed if previous risk was not Orange (or is None)
        if self.previous_risk_level != "Orange":
            return False
        
        # First time detecting risk (no previous timestamp), send alert
        if self.risk_level_timestamp is None:
            logger.info("First time detecting risk level, will send alert if needed.")
            return True
            
        # Check if we've already alerted for this transition
        if self.last_alerted_timestamp is not None:
            # If the risk level was set AFTER the last alert, this could be a new transition
            if self.risk_level_timestamp > self.last_alerted_timestamp:
                if not ignore_daily_limit: # Only check daily limit if not ignoring
                    current_date = current_time.date()
                    last_alert_date = self.last_alerted_timestamp.date()
                    
                    if current_date == last_alert_date:
                        logger.info(f"Already sent an Orange-to-Red alert today ({current_date}). Limiting to once per calendar day. (ignore_daily_limit={ignore_daily_limit})")
                        return False
                    else:
                        logger.info(f"New transition detected on a new calendar day. Last alert was on {last_alert_date}, today is {current_date}. (ignore_daily_limit={ignore_daily_limit})")
                        return True # New day, send alert
                else: # Ignoring daily limit
                    logger.info(f"Ignoring daily email limit for this check. New transition detected after last alert.")
                    return True # Ignoring daily limit, new transition after last alert means send
            else: # Risk level timestamp is not after last alerted timestamp
                logger.info(f"Already alerted for this specific risk transition instance at {self.last_alerted_timestamp.isoformat()}. (ignore_daily_limit={ignore_daily_limit})")
                return False
        
        # Haven't alerted yet for this transition (last_alerted_timestamp is None, or conditions above met)
        logger.info(f"Conditions met to send alert (or first alert). (ignore_daily_limit={ignore_daily_limit})")
        return True
    
    def update_risk_level(self, risk_level: str) -> None:
        """Update the stored risk level with timestamp.
        
        Args:
            risk_level: The new risk level
        """
        current_time = datetime.now(TIMEZONE)
        
        # Only update timestamp if risk level changes
        if risk_level != self.previous_risk_level:
            logger.info(f"Risk level changed from {self.previous_risk_level} to {risk_level}")
            self.risk_level_timestamp = current_time
            self.previous_risk_level = risk_level
            # Save to disk immediately to ensure persistence
            self._save_cache_to_disk()
        
    def record_alert_sent(self) -> None:
        """Record that an alert was sent for the current risk transition."""
        self.last_alerted_timestamp = datetime.now(TIMEZONE)
        # Save to disk immediately to prevent duplicate alerts
        self._save_cache_to_disk()
        
    def ensure_complete_weather_data(self, weather_data: Dict[str, Any], use_default_if_missing: bool = False) -> Dict[str, Any]:
        """Ensure all required weather fields have values, filling in missing ones from cache
        
        Args:
            weather_data: The weather data dictionary to validate and complete
            use_default_if_missing: If True, use default values instead of cached values when filling missing fields
            
        Returns:
            The completed weather data with no None values for critical fields
        """
        # Make a copy to avoid modifying the original
        completed_data = weather_data.copy()
        
        # Map from API response field name to internal field name
        field_mapping = {
            "air_temp": "temperature",
            "relative_humidity": "humidity",
            "wind_speed": "wind_speed",
            "soil_moisture_15cm": "soil_moisture",
            "wind_gust": "wind_gust"
        }
        
        # Ensure each field has a value
        for api_field, internal_field in field_mapping.items():
            if api_field not in completed_data or completed_data[api_field] is None:
                # Field is missing or None, get a value for it
                value = self.get_field_value(internal_field, use_default_if_missing)
                completed_data[api_field] = value
                logger.info(f"Added missing {api_field} value: {value}")
        
        return completed_data

# Initialize the cache
data_cache = DataCache()

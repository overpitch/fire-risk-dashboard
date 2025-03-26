import threading
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import pytz

from config import TIMEZONE, logger

class DataCache:
    def __init__(self):
        self.synoptic_data: Optional[Dict[str, Any]] = None
        self.wunderground_data: Optional[Dict[str, Any]] = None
        self.fire_risk_data: Optional[Dict[str, Any]] = None
        self.last_updated: Optional[datetime] = None
        self.update_in_progress: bool = False
        self.last_update_success: bool = False
        self.max_retries: int = 5  # Increased from 3 to 5
        self.retry_delay: int = 5  # seconds
        self.update_timeout: int = 15  # seconds - max time to wait for a complete refresh
        self.background_refresh_interval: int = 10  # minutes
        self.data_timeout_threshold: int = 30  # minutes - max age before data is considered too old
        self.refresh_task_active: bool = False
        # Lock for thread safety
        self._lock = threading.Lock()
        # Event to signal when an update is complete
        self._update_complete_event = asyncio.Event()
        # Storage for last known valid data by field
        self.last_valid_data: Dict[str, Any] = {
            # Store each weather field individually with its own timestamp
            "fields": {
                "temperature": {"value": None, "timestamp": None},
                "humidity": {"value": None, "timestamp": None},
                "wind_speed": {"value": None, "timestamp": None},
                "soil_moisture": {"value": None, "timestamp": None},
                "wind_gust": {"value": None, "timestamp": None}
            },
            # Keep the whole API responses for backwards compatibility
            "synoptic_data": None,
            "wunderground_data": None,
            "fire_risk_data": None,
            "timestamp": None,
        }
        # Track which fields are currently using cached data
        self.cached_fields: Dict[str, bool] = {
            "temperature": False,
            "humidity": False,
            "wind_speed": False,
            "soil_moisture": False,
            "wind_gust": False
        }
        # Flag to indicate if we're currently using any cached data
        self.using_cached_data: bool = False

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
    
    def update_cache(self, synoptic_data, wunderground_data, fire_risk_data):
        """Update the cache with new data"""
        # Create timezone-aware datetime for Pacific timezone
        current_time = datetime.now(TIMEZONE)
        
        # Store the current cached_fields and using_cached_data state
        cached_fields_state = self.cached_fields.copy()
        using_cached_data_state = self.using_cached_data
        
        with self._lock:
            self.synoptic_data = synoptic_data
            self.wunderground_data = wunderground_data
            
            # If we're using cached data, make sure the fire_risk_data has a cached_data field
            if using_cached_data_state and "cached_data" not in fire_risk_data:
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
                        "cached_fields": cached_fields_state.copy()
                    }
            
            self.fire_risk_data = fire_risk_data
            self.last_updated = current_time
            self.last_update_success = True
            
            # Restore the cached_fields and using_cached_data state
            self.cached_fields = cached_fields_state
            self.using_cached_data = using_cached_data_state
            
            # Store the full response data for backwards compatibility
            if synoptic_data is not None or wunderground_data is not None:
                self.last_valid_data["synoptic_data"] = synoptic_data
                self.last_valid_data["wunderground_data"] = wunderground_data
                self.last_valid_data["fire_risk_data"] = fire_risk_data
                self.last_valid_data["timestamp"] = current_time
                
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
                    
                    if weather.get("wind_gust") is not None:
                        self.last_valid_data["fields"]["wind_gust"]["value"] = weather["wind_gust"]
                        self.last_valid_data["fields"]["wind_gust"]["timestamp"] = current_time
                
                logger.info(f"Stored valid data for future fallback use at {current_time}")
            
            # Set the event to signal update completion
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_closed():
                    loop.call_soon_threadsafe(self._update_complete_event.set)
            except Exception as e:
                logger.error(f"Error signaling update completion: {e}")
        
        # Log cache update
        logger.info(f"Cache updated at {self.last_updated}")
    
    def reset_update_event(self):
        """Reset the update complete event for next update cycle"""
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                loop.call_soon_threadsafe(self._update_complete_event.clear)
        except Exception as e:
            logger.error(f"Error resetting update event: {e}")
    
    async def wait_for_update(self, timeout=None):
        """Wait for the current update to complete, with an optional timeout"""
        if timeout is None:
            timeout = self.update_timeout
        try:
            await asyncio.wait_for(self._update_complete_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for data update after {timeout} seconds")
            return False

# Initialize the cache
data_cache = DataCache()

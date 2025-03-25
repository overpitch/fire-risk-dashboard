from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta, timezone
import requests
import os
import logging
import sys
import importlib.metadata
import json
import time
import threading
import asyncio
from typing import Dict, Any, Optional, Callable, Tuple
import pytz
import functools
from pydantic import BaseModel

# Initialize Jinja2Templates
templates = Jinja2Templates(directory="templates")

# Only load .env for local development (not on Render)
if os.getenv("RENDER") is None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("Loaded .env file for local development.")
    except ImportError:
        print("python-dotenv is not installed. Skipping .env loading.")

# Determine if we're running in production mode
IS_PRODUCTION = os.getenv("RENDER") is not None

# Decorator to conditionally register endpoints based on environment
def dev_only_endpoint(func):
    """Decorator to make an endpoint available only in development mode."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        if IS_PRODUCTION:
            # In production, return a 404 Not Found
            raise HTTPException(status_code=404, detail="Endpoint not available in production")
        return await func(*args, **kwargs)
    return wrapper

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# API Configuration
SYNOPTIC_API_KEY = os.getenv("SYNOPTICDATA_API_KEY")
SYNOPTIC_BASE_URL = "https://api.synopticdata.com/v2"
# Weather Underground API
WUNDERGROUND_API_KEY = os.getenv("WUNDERGROUND_API_KEY")
WUNDERGROUND_BASE_URL = "https://api.weather.com/v2/pws"
# Station IDs (hard-coded)
SOIL_MOISTURE_STATION_ID = "C3DLA"  # Station for soil moisture data
WEATHER_STATION_ID = "SEYC1"        # Station for temperature, humidity, and winds
WUNDERGROUND_STATION_ID = "KCASIERR68"  # Station for wind gusts data

if not SYNOPTIC_API_KEY:
    logger.warning("No API key provided. Set SYNOPTICDATA_API_KEY environment variable.")

if not WUNDERGROUND_API_KEY:
    logger.warning("No Weather Underground API key provided. Set WUNDERGROUND_API_KEY environment variable.")

app = FastAPI()

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Fire risk thresholds from environment variables
THRESH_TEMP = float(os.getenv("THRESH_TEMP", 75))            # Temperature threshold in Fahrenheit
THRESH_HUMID = float(os.getenv("THRESH_HUMID", 15))          # Humidity threshold in percent
THRESH_WIND = float(os.getenv("THRESH_WIND", 15))            # Wind speed threshold in mph
THRESH_GUSTS = float(os.getenv("THRESH_GUSTS", 20))          # Wind gust threshold in mph
THRESH_SOIL_MOIST = float(os.getenv("THRESH_SOIL_MOIST", 10)) # Soil moisture threshold in percent

# Convert temperature threshold from Fahrenheit to Celsius for internal use
THRESH_TEMP_CELSIUS = (THRESH_TEMP - 32) * 5/9

logger.info(f"Using thresholds: TEMP={THRESH_TEMP}°F, "
            f"HUMID={THRESH_HUMID}%, WIND={THRESH_WIND}mph, "
            f"GUSTS={THRESH_GUSTS}mph, SOIL={THRESH_SOIL_MOIST}%")


# Cache for weather data and fire risk with improved reliability
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
        """Check if the data is stale (older than max_age_minutes)."""
        if self.last_updated is None:
            return True
        # Use timezone-aware comparison
        pacific_tz = pytz.timezone('America/Los_Angeles')
        now = datetime.now(pacific_tz)
        age = now - self.last_updated
        return age > timedelta(minutes=max_age_minutes)

    def is_critically_stale(self) -> bool:
        """Check if the data is critically stale (older than data_timeout_threshold)."""
        if self.last_updated is None:
            return True
        # Use timezone-aware comparison
        pacific_tz = pytz.timezone('America/Los_Angeles')
        now = datetime.now(pacific_tz)
        age = now - self.last_updated
        return age > timedelta(minutes=self.data_timeout_threshold)

    def update_cache(self, synoptic_data, wunderground_data, fire_risk_data):
        """Update the cache with new data."""
        logger.info(f"Updating cache with fire_risk_data: {fire_risk_data}")

        with self._lock:
            pacific_tz = pytz.timezone('America/Los_Angeles')
            current_time = datetime.now(pacific_tz)

            self.synoptic_data = synoptic_data
            self.wunderground_data = wunderground_data
            self.fire_risk_data = fire_risk_data
            self.last_updated = current_time
            self.last_update_success = True

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

            try:
            loop = asyncio.get_event_loop()
        except Exception as e:
                logger.error(f"Error getting event loop: {e}")
                if not loop.is_closed():
                    loop.call_soon_threadsafe(self._update_complete_event.set)
            except Exception as e:
                logger.error(f"Error signaling update completion: {e}")

        logger.info(f"Cache updated at {self.last_updated}")

    def reset_update_event(self):
        """Reset the update complete event for next update cycle."""
        try:
                loop = asyncio.get_event_loop()
            except Exception as e:
                logger.error(f"Error getting event loop: {e}")
            if not loop.is_closed():
                loop.call_soon_threadsafe(self._update_complete_event.clear)
        except Exception as e:
            logger.error(f"Error resetting update event: {e}")

    async def wait_for_update(self, timeout=None):
        """Wait for the current update to complete, with an optional timeout."""
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


async def refresh_data_cache(background_tasks: BackgroundTasks = None, force: bool = False):
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
            station_ids = f"{SOIL_MOISTURE_STATION_ID},{WEATHER_STATION_ID}"
            # Use the retry mechanism built into get_weather_data
            return get_weather_data(station_ids)
            
        def fetch_wunderground():
            return get_wunderground_data(WUNDERGROUND_STATION_ID)
        
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
    
    while not success and retries < data_cache.max_retries:
        try:
            # Check if we're exceeding our total timeout
            if time.time() - start_time > data_cache.update_timeout:
                logger.warning(f"Data refresh taking too long (over {data_cache.update_timeout}s), aborting")
                break
                
            # Fetch data from both APIs concurrently
            weather_data, wunderground_data = await fetch_all_data()
            
            # Initialize variables to store data from each station with default values
            soil_moisture_15cm = None
            air_temp = None
            relative_humidity = None
            wind_speed = None
            wind_gust = None
            
            # Track which stations were found in the response
            found_stations = []
            missing_stations = []
            data_issues = []
            
            # Process Weather Underground data for wind gusts
            if not wunderground_data:
                logger.error("Failed to get Weather Underground data")
                data_issues.append(f"Failed to fetch wind gust data from Weather Underground station {WUNDERGROUND_STATION_ID}")
            else:
                try:
                    # Extract wind gust data from the response
                    observations = wunderground_data.get("observations", [])
                    if observations and len(observations) > 0:
                        # The first observation contains the current conditions
                        current = observations[0]
                        wind_gust = current.get("imperial", {}).get("windGust")
                        found_stations.append(WUNDERGROUND_STATION_ID)
                        logger.info(f"Found wind gust data: {wind_gust} mph from station {WUNDERGROUND_STATION_ID}")
                    else:
                        missing_stations.append(WUNDERGROUND_STATION_ID)
                        data_issues.append(f"No wind gust data available from Weather Underground station {WUNDERGROUND_STATION_ID}")
                except Exception as e:
                    logger.error(f"Error processing Weather Underground data: {str(e)}")
                    data_issues.append(f"Error processing wind gust data: {str(e)}")
            
            # Process Synoptic weather data
            synoptic_data_valid = False
            if not weather_data:
                logger.error("Failed to get any weather data from Synoptic API")
                data_issues.append("Failed to fetch weather data from Synoptic API")
            elif "STATION" not in weather_data:
                logger.error("Weather API response missing STATION data")
                data_issues.append("Invalid response format from Synoptic API")
            else:
                stations = weather_data["STATION"]
                synoptic_data_valid = True
                
                # Check if we received data for expected stations
                station_ids_in_response = [station.get("STID") for station in stations]
                logger.info(f"Received data for stations: {station_ids_in_response}")
                
                if SOIL_MOISTURE_STATION_ID not in station_ids_in_response:
                    missing_stations.append(SOIL_MOISTURE_STATION_ID)
                    data_issues.append(f"No data received from soil moisture station {SOIL_MOISTURE_STATION_ID}")
                
                if WEATHER_STATION_ID not in station_ids_in_response:
                    missing_stations.append(WEATHER_STATION_ID)
                    data_issues.append(f"No data received from weather station {WEATHER_STATION_ID}")
                
                # Process data from each station
                for station in stations:
                    station_id = station.get("STID")
                    found_stations.append(station_id)
                    observations = station.get("OBSERVATIONS", {})
                    
                    if station_id == SOIL_MOISTURE_STATION_ID:
                        # For C3DLA: Get soil moisture data
                        soil_moisture_keys = [k for k in observations.keys() if 'soil_moisture' in k]
                        logger.info(f"Available soil moisture keys from {station_id}: {soil_moisture_keys}")
                        
                        # Check for soil moisture at 0.15m depth specifically
                        for key in soil_moisture_keys:
                            if '0.15' in key or '15cm' in key or '15_cm' in key:
                                soil_moisture_15cm = observations.get(key, {}).get("value")
                                logger.info(f"Found soil moisture at 0.15m: {soil_moisture_15cm} from key {key}")
                                break
                        
                        # If we didn't find 0.15m specific measurement, look for soil_moisture_value_1
                        if soil_moisture_15cm is None:
                            soil_moisture_15cm = observations.get("soil_moisture_value_1", {}).get("value")
                            logger.info(f"Using default soil_moisture_value_1: {soil_moisture_15cm}")
                            
                        if soil_moisture_15cm is None:
                            data_issues.append(f"No soil moisture data available from station {SOIL_MOISTURE_STATION_ID}")
                            
                    elif station_id == WEATHER_STATION_ID:
                        # For CEYC1: Get temperature, humidity, and wind data
                        air_temp = observations.get("air_temp_value_1", {}).get("value")
                        relative_humidity = observations.get("relative_humidity_value_1", {}).get("value")
                        wind_speed = observations.get("wind_speed_value_1", {}).get("value")
                        
                        # Check if we got all required weather data
                        if air_temp is None:
                            data_issues.append(f"Temperature data missing from station {WEATHER_STATION_ID}")
                        if relative_humidity is None:
                            data_issues.append(f"Humidity data missing from station {WEATHER_STATION_ID}")
                        if wind_speed is None:
                            data_issues.append(f"Wind data missing from station {WEATHER_STATION_ID}")
            
            # Combine the data from all stations
            latest_weather = {
                "air_temp": air_temp,
                "relative_humidity": relative_humidity,
                "wind_speed": wind_speed,
                "soil_moisture_15cm": soil_moisture_15cm,
                "wind_gust": wind_gust,  # Add the wind gust data
                # Add station information for UI display
                "data_sources": {
                    "weather_station": WEATHER_STATION_ID,
                    "soil_moisture_station": SOIL_MOISTURE_STATION_ID,
                    "wind_gust_station": WUNDERGROUND_STATION_ID  # Add the wind gust station
                },
                "data_status": {
                    "found_stations": found_stations,
                    "missing_stations": missing_stations,
                    "issues": data_issues
                },
                # Use timezone-aware datetime
                "cache_timestamp": datetime.now(pytz.timezone('America/Los_Angeles')).isoformat()
            }

            # Check for individual fields that are missing and use cached values where available
            pacific_tz = pytz.timezone('America/Los_Angeles')
            current_time = datetime.now(pacific_tz)
            any_field_using_cache = False
            cached_fields_info = []
            
            # Add each field to data_issues if it's missing
            if air_temp is None:
                missing_field = f"Temperature data missing from station {WEATHER_STATION_ID}"
                if missing_field not in data_issues:
                    data_issues.append(missing_field)
                    
            if relative_humidity is None:
                missing_field = f"Humidity data missing from station {WEATHER_STATION_ID}"
                if missing_field not in data_issues:
                    data_issues.append(missing_field)
                    
            if wind_speed is None:
                missing_field = f"Wind speed data missing from station {WEATHER_STATION_ID}"
                if missing_field not in data_issues:
                    data_issues.append(missing_field)
                    
            if soil_moisture_15cm is None:
                missing_field = f"Soil moisture data missing from station {SOIL_MOISTURE_STATION_ID}"
                if missing_field not in data_issues:
                    data_issues.append(missing_field)
                    
            if wind_gust is None:
                missing_field = f"Wind gust data missing from station {WUNDERGROUND_STATION_ID}"
                if missing_field not in data_issues:
                    data_issues.append(missing_field)
            
            # Now check the cache for any missing fields and use if available
            if soil_moisture_15cm is None and data_cache.last_valid_data["fields"]["soil_moisture"]["value"] is not None:
                soil_moisture_15cm = data_cache.last_valid_data["fields"]["soil_moisture"]["value"]
                data_cache.cached_fields["soil_moisture"] = True
                any_field_using_cache = True
                
                cached_time = data_cache.last_valid_data["fields"]["soil_moisture"]["timestamp"]
                age_delta = current_time - cached_time
                # Calculate age string
                if age_delta.days > 0:
                    age_str = f"{age_delta.days} day{'s' if age_delta.days != 1 else ''}"
                elif age_delta.seconds // 3600 > 0:
                    hours = age_delta.seconds // 3600
                    age_str = f"{hours} hour{'s' if hours != 1 else ''}"
                else:
                    minutes = age_delta.seconds // 60
                    age_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
                
                logger.info(f"Using cached soil moisture data: {soil_moisture_15cm}% from {cached_time.isoformat()} ({age_str} old)")
                
                # Store info about this cached field
                cached_fields_info.append({
                    "field": "soil_moisture",
                    "value": soil_moisture_15cm,
                    "timestamp": cached_time,
                    "age": age_str
                })
            
            if air_temp is None and data_cache.last_valid_data["fields"]["temperature"]["value"] is not None:
                air_temp = data_cache.last_valid_data["fields"]["temperature"]["value"]
                data_cache.cached_fields["temperature"] = True
                any_field_using_cache = True
                
                cached_time = data_cache.last_valid_data["fields"]["temperature"]["timestamp"]
                age_delta = current_time - cached_time
                # Calculate age string
                if age_delta.days > 0:
                    age_str = f"{age_delta.days} day{'s' if age_delta.days != 1 else ''}"
                elif age_delta.seconds // 3600 > 0:
                    hours = age_delta.seconds // 3600
                    age_str = f"{hours} hour{'s' if hours != 1 else ''}"
                else:
                    minutes = age_delta.seconds // 60
                    age_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
                
                logger.info(f"Using cached temperature data: {air_temp}°C from {cached_time.isoformat()} ({age_str} old)")
                
                # Store info about this cached field
                cached_fields_info.append({
                    "field": "temperature",
                    "value": air_temp,
                    "timestamp": cached_time,
                    "age": age_str
                })
            
            if relative_humidity is None and data_cache.last_valid_data["fields"]["humidity"]["value"] is not None:
                relative_humidity = data_cache.last_valid_data["fields"]["humidity"]["value"]
                data_cache.cached_fields["humidity"] = True
                any_field_using_cache = True
                
                cached_time = data_cache.last_valid_data["fields"]["humidity"]["timestamp"]
                age_delta = current_time - cached_time
                # Calculate age string
                if age_delta.days > 0:
                    age_str = f"{age_delta.days} day{'s' if age_delta.days != 1 else ''}"
                elif age_delta.seconds // 3600 > 0:
                    hours = age_delta.seconds // 3600
                    age_str = f"{hours} hour{'s' if hours != 1 else ''}"
                else:
                    minutes = age_delta.seconds // 60
                    age_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
                
                logger.info(f"Using cached humidity data: {relative_humidity}% from {cached_time.isoformat()} ({age_str} old)")
                
                # Store info about this cached field
                cached_fields_info.append({
                    "field": "humidity",
                    "value": relative_humidity,
                    "timestamp": cached_time,
                    "age": age_str
                })
            
            if wind_speed is None and data_cache.last_valid_data["fields"]["wind_speed"]["value"] is not None:
                wind_speed = data_cache.last_valid_data["fields"]["wind_speed"]["value"]
                data_cache.cached_fields["wind_speed"] = True
                any_field_using_cache = True
                
                cached_time = data_cache.last_valid_data["fields"]["wind_speed"]["timestamp"]
                age_delta = current_time - cached_time
                # Calculate age string
                if age_delta.days > 0:
                    age_str = f"{age_delta.days} day{'s' if age_delta.days != 1 else ''}"
                elif age_delta.seconds // 3600 > 0:
                    hours = age_delta.seconds // 3600
                    age_str = f"{hours} hour{'s' if hours != 1 else ''}"
                else:
                    minutes = age_delta.seconds // 60
                    age_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
                
                logger.info(f"Using cached wind speed data: {wind_speed} mph from {cached_time.isoformat()} ({age_str} old)")
                
                # Store info about this cached field
                cached_fields_info.append({
                    "field": "wind_speed",
                    "value": wind_speed,
                    "timestamp": cached_time,
                    "age": age_str
                })
            
            if wind_gust is None and data_cache.last_valid_data["fields"]["wind_gust"]["value"] is not None:
                wind_gust = data_cache.last_valid_data["fields"]["wind_gust"]["value"]
                data_cache.cached_fields["wind_gust"] = True
                any_field_using_cache = True
                
                cached_time = data_cache.last_valid_data["fields"]["wind_gust"]["timestamp"]
                age_delta = current_time - cached_time
                # Calculate age string
                if age_delta.days > 0:
                    age_str = f"{age_delta.days} day{'s' if age_delta.days != 1 else ''}"
                elif age_delta.seconds // 3600 > 0:
                    hours = age_delta.seconds // 3600
                    age_str = f"{hours} hour{'s' if hours != 1 else ''}"
                else:
                    minutes = age_delta.seconds // 60
                    age_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
                
                logger.info(f"Using cached wind gust data: {wind_gust} mph from {cached_time.isoformat()} ({age_str} old)")
                
                # Store info about this cached field
                cached_fields_info.append({
                    "field": "wind_gust",
                    "value": wind_gust,
                    "timestamp": cached_time,
                    "age": age_str
                })
            
            # Update the global cache flag if any fields are using cached data
            data_cache.using_cached_data = any_field_using_cache
            
            # If both APIs failed and we have no cached data for any field, then we have a complete failure
            if not synoptic_data_valid and not wunderground_data and not any_field_using_cache:
                logger.warning("All critical data sources failed and no cached data available")
                raise ValueError("All critical data sources failed and no cached data available")
            
            # Update the latest_weather with the final values (including cached ones)
            latest_weather["air_temp"] = air_temp
            latest_weather["relative_humidity"] = relative_humidity
            latest_weather["wind_speed"] = wind_speed
            latest_weather["soil_moisture_15cm"] = soil_moisture_15cm
            latest_weather["wind_gust"] = wind_gust
            latest_weather["cached_fields"] = data_cache.cached_fields.copy()
            
            # Process the data and calculate fire risk
            risk, explanation = calculate_fire_risk(latest_weather)
            
            # If we had data issues, add a note to the explanation
            if data_issues:
                explanation += " Note: Some data sources were unavailable."
            
            # If we're using any cached data, add a note to the explanation
            if any_field_using_cache:
                explanation += " Some values are from cached data."
                
                # Add a notice about using cached data
                cached_time = data_cache.last_valid_data["timestamp"]
                if cached_time:
                    age_delta = current_time - cached_time
                    if age_delta.days > 0:
                        age_str = f"{age_delta.days} day{'s' if age_delta.days != 1 else ''}"
                    elif age_delta.seconds // 3600 > 0:
                        hours = age_delta.seconds // 3600
                        age_str = f"{hours} hour{'s' if hours != 1 else ''}"
                    else:
                        minutes = age_delta.seconds // 60
                        age_str = f"{minutes} minute{'s' if minutes != 1 else ''}"

def get_api_token():
    """Get a temporary API token using the permanent API key."""
    api_key = os.getenv("SYNOPTICDATA_API_KEY")
    if not api_key:
        logger.error("🚨 API KEY NOT FOUND! Environment variable is missing.")
        return None

    try:
        token_url = f"{SYNOPTIC_BASE_URL}/auth?apikey={api_key}"
        logger.info(f"🔎 DEBUG: Fetching API token from {token_url}")

        response = requests.get(token_url)
        response.raise_for_status()
        token_data = response.json()

        # Log the full token response for debugging
        logger.info(f"🔎 DEBUG: Token response: {json.dumps(token_data)}")

        token = token_data.get("TOKEN")  # ✅ Extract token correctly
        if token:
            logger.info(f"✅ Received API token: {token[:5]}... (truncated)")
        else:
            logger.error("🚨 Token was empty or missing in response.")
            # Check if there's an error message in the response
            if "error" in token_data:
                logger.error(f"🚨 API error message: {token_data['error']}")

        return token

    except requests.exceptions.RequestException as e:
        logger.error(f"🚨 Error fetching API token: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                logger.error(f"🚨 API error details: {json.dumps(error_data)}")
            except:
                logger.error(f"🚨 API error status code: {e.response.status_code}")
                logger.error(f"🚨 API error response text: {e.response.text[:200]}")
        return None

def get_weather_data(location_ids, retry_count=0, max_retries=2):
    """Get weather data using the temporary token.
    
    Args:
        location_ids: A string of comma-separated station IDs
        retry_count: Current retry attempt (used internally for recursion)
        max_retries: Maximum number of retries for 401 errors
    """
    token = get_api_token()
    if not token:
        return None

    try:
        # Construct the full URL for logging purposes
        request_url = f"{SYNOPTIC_BASE_URL}/stations/latest?stid={location_ids}&token={token}"
        # Log the URL with the token partially masked for security
        masked_url = f"{SYNOPTIC_BASE_URL}/stations/latest?stid={location_ids}&token={token[:5]}..."
        logger.info(f"🔎 DEBUG: Making API request to {masked_url}")

        response = requests.get(request_url)
        
        # Log the response status code
        logger.info(f"🔎 DEBUG: API response status code: {response.status_code}")
        
        # Check for specific error codes
        if response.status_code == 401:
            logger.error("🚨 Authentication failed (401 Unauthorized). The API token may be invalid or expired.")
            # Try to get error details from response
            try:
                error_data = response.json()
                logger.error(f"🚨 API error details: {json.dumps(error_data)}")
            except:
                logger.error(f"🚨 API error response text: {response.text[:200]}")
            
            # If we haven't exceeded max retries, get a fresh token and try again
            if retry_count < max_retries:
                logger.info(f"🔄 Retrying with a fresh token (attempt {retry_count + 1}/{max_retries})")
                # Force a new token by clearing any cached token (if we had token caching)
                # Then recursively call this function with incremented retry count
                return get_weather_data(location_ids, retry_count + 1, max_retries)
            else:
                logger.error(f"❌ Exceeded maximum retries ({max_retries}) for 401 errors")
                return None
        
        response.raise_for_status()
        data = response.json()
        
        # Log a snippet of the response data
        logger.info(f"✅ Successfully received data from Synoptic API")
        
        return data

    except requests.exceptions.RequestException as e:
        logger.error(f"Exception during API request: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                logger.error(f"🚨 API error details: {json.dumps(error_data)}")
            except:
                logger.error(f"🚨 API error status code: {e.response.status_code}")
                logger.error(f"🚨 API error response text: {e.response.text[:200]}")
        return None

def get_wunderground_data(station_id):
    """Get weather data from Weather Underground API.
    
    Args:
        station_id: The Weather Underground station ID (e.g. KCASIERR68)
    
    Returns:
        Dictionary containing the weather data or None if an error occurred
    """
    api_key = os.getenv("WUNDERGROUND_API_KEY")
    if not api_key:
        logger.error("🚨 WEATHER UNDERGROUND API KEY NOT FOUND! Environment variable is missing.")
        return None
    
    try:
        # Build the URL to get the current conditions for the station
        url = f"{WUNDERGROUND_BASE_URL}/observations/current?stationId={station_id}&format=json&units=e&apiKey={api_key}"
        logger.info(f"🔎 Fetching Weather Underground data for station {station_id}")
        
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Check if we have the expected data structure
        if "observations" in data and len(data["observations"]) > 0:
            logger.info(f"✅ Successfully received data from Weather Underground for station {station_id}")
            return data
        else:
            logger.error(f"🚨 No observations found in Weather Underground response for station {station_id}")
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"🚨 Error fetching Wind Gust data from Weather Underground: {e}")
        return None

def calculate_fire_risk(weather):
    """Determines fire risk level based on weather data and environmental thresholds."""
    try:
        # Ensure we have valid values by providing defaults if values are None
        air_temp = weather.get("air_temp")
        relative_humidity = weather.get("relative_humidity")
        wind_speed = weather.get("wind_speed")
        wind_gust = weather.get("wind_gust")
        soil_moisture_15cm = weather.get("soil_moisture_15cm")
        
        # Log the received values for debugging
        logger.info(f"Received weather data: temp={air_temp}°C, humidity={relative_humidity}%, "
                    f"wind={wind_speed}mph, gusts={wind_gust}mph, soil={soil_moisture_15cm}%")
        
        # Use defaults if values are None
        temp = float(0 if air_temp is None else air_temp)
        humidity = float(100 if relative_humidity is None else relative_humidity)
        wind = float(0 if wind_speed is None else wind_speed)
        gusts = float(0 if wind_gust is None else wind_gust)
        soil = float(100 if soil_moisture_15cm is None else soil_moisture_15cm)
        
        # Check if all thresholds are exceeded
        temp_exceeded = temp > THRESH_TEMP_CELSIUS
        humidity_exceeded = humidity < THRESH_HUMID
        wind_exceeded = wind > THRESH_WIND
        gusts_exceeded = gusts > THRESH_GUSTS
        soil_exceeded = soil < THRESH_SOIL_MOIST
        
        # Log threshold checks
        logger.info(f"Threshold checks: temp={temp_exceeded}, humidity={humidity_exceeded}, "
                    f"wind={wind_exceeded}, gusts={gusts_exceeded}, soil={soil_exceeded}")
        
        # If all thresholds are exceeded: RED, otherwise: ORANGE
        if temp_exceeded and humidity_exceeded and wind_exceeded and gusts_exceeded and soil_exceeded:
            return "Red", "High fire risk due to high temperature, low humidity, strong winds, high wind gusts, and low soil moisture."
        else:
            return "Orange", "Low or Moderate Fire Risk. Exercise standard prevention practices."

    except Exception as e:
        logger.error(f"Error calculating fire risk: {str(e)}")
        return "Error", f"Could not calculate risk: {str(e)}"

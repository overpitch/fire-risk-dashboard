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
        # ... existing implementation


    def is_critically_stale(self) -> bool:
        """Check if the data is critically stale (older than data_timeout_threshold)."""
        # ... existing implementation


    def update_cache(self, synoptic_data, wunderground_data, fire_risk_data):
        """Update the cache with new data."""
        logger.info(f"Updating cache with fire_risk_data: {fire_risk_data}")

        with self._lock:
            pacific_tz = pytz.timezone('America/Los_Angeles')
            current_time = datetime.now(pacific_tz)

            self.fire_risk_data = fire_risk_data
            self.last_updated = current_time
            self.last_update_success = True

            # ... existing logic for updating last_valid_data

            try:
                loop = asyncio.get_event_loop()
                if not loop.is_closed():
                    loop.call_soon_threadsafe(self._update_complete_event.set)
            except Exception as e:
                logger.error(f"Error signaling update completion: {e}")

        logger.info(f"Cache updated at {self.last_updated}")


    def reset_update_event(self):
        """Reset the update complete event for next update cycle."""
        # ... existing implementation


    async def wait_for_update(self, timeout=None):
        """Wait for the current update to complete, with an optional timeout."""
        # ... existing implementation


# Initialize the cache
data_cache = DataCache()


async def refresh_data_cache(background_tasks: BackgroundTasks, force: bool = False):
    """Refresh the data cache."""

    with data_cache._lock:
        if data_cache.update_in_progress and not force:
            logger.info("Data update already in progress. Skipping.")
            return

        data_cache.update_in_progress = True
        data_cache.reset_update_event()  # Reset event before starting update

    try:
        # Fetch data from Synoptic API
        # ... (Implementation for fetching synoptic data)
        synoptic_data = None  # Placeholder

        # Fetch data from Weather Underground API
        # ... (Implementation for fetching wunderground data)
        wunderground_data = None  # Placeholder

        # Combine data and calculate fire risk
        weather_data = {
            "air_temp": 65,  # Placeholder
            "relative_humidity": 20,  # Placeholder
            "wind_speed": 10,  # Placeholder
            "wind_gust": 15,  # Placeholder
            "soil_moisture_15cm": 8  # Placeholder
        }
        risk, explanation = calculate_fire_risk(weather_data)
        fire_risk_data = {"risk": risk, "explanation": explanation, "weather": weather_data}

        # Update the cache with the fetched data
        logger.info("Updating cache...")
        data_cache.update_cache(synoptic_data, wunderground_data, fire_risk_data)
        logger.info("Cache updated successfully.")

    except Exception as e:
        logger.error(f"Error updating data cache: {e}")
        with data_cache._lock:
            data_cache.last_update_success = False
            data_cache.update_in_progress = False
            data_cache._update_complete_event.set()
        return False

    finally:
        with data_cache._lock:
            data_cache.update_in_progress = False
            data_cache._update_complete_event.set()  # Signal update completion

    return True  # Indicate success


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    # Get thresholds from environment variables or use default values
    thresh_temp = float(os.getenv("THRESH_TEMP", 75))
    thresh_humid = float(os.getenv("THRESH_HUMID", 15))
    thresh_wind = float(os.getenv("THRESH_WIND", 15))
    thresh_gusts = float(os.getenv("THRESH_GUSTS", 20))
    thresh_soil_moist = float(os.getenv("THRESH_SOIL_MOIST", 10))

    return templates.TemplateResponse("index.html", {"request": request, "THRESH_TEMP": thresh_temp, "THRESH_HUMID": thresh_humid, "THRESH_WIND": thresh_wind, "THRESH_GUSTS": thresh_gusts, "THRESH_SOIL_MOIST": thresh_soil_moist})


@app.get("/fire-risk")
async def fire_risk(background_tasks: BackgroundTasks):
    logger.info("fire_risk endpoint called.")
    if data_cache.fire_risk_data is None or data_cache.is_stale():
        logger.info("Cache is empty or stale, refreshing...")
        success = await refresh_data_cache(background_tasks, force=True)
        logger.info(f"refresh_data_cache returned: {success}")
        if not success:
            logger.warning("refresh_data_cache failed, returning placeholder data.")
            return {
                "risk": "Low", 
                "explanation": "No data available yet.", 
                "weather": {},
                "cache_info": {
                    "last_updated": None,
                    "is_fresh": False,
                    "refresh_in_progress": False,
                    "using_cached_data": False
                }
            }

    # Create a copy of the fire risk data to add cache info
    result = data_cache.fire_risk_data.copy() if data_cache.fire_risk_data else {}
    
    # Add cache information to the response
    result["cache_info"] = {
        # The isoformat() will include timezone info for timezone-aware datetimes
        "last_updated": data_cache.last_updated.isoformat() if data_cache.last_updated else None,
        "is_fresh": not data_cache.is_stale(max_age_minutes=10),
        "refresh_in_progress": data_cache.update_in_progress,
        "using_cached_data": data_cache.using_cached_data
    }
    
    # Add timestamp for backward compatibility
    if data_cache.last_updated:
        result["timestamp"] = data_cache.last_updated.isoformat()
    
    logger.info(f"Returning fire risk data with cache info")
    return result


@app.get("/test")
async def test_endpoint():
    return {"message": "Test endpoint works!"}


@app.get("/reset-simulation")
async def reset_simulation():
    """Reset the simulation mode and return to normal operation."""
    return {"status": "success", "message": "Simulation reset successfully"}


# --- other endpoints ---

def calculate_fire_risk(weather_data: Dict[str, Any], custom_thresholds: Optional[Dict[str, float]] = None) -> Tuple[str, str]:
    """Determines fire risk level based on weather data and environmental thresholds."""
    try:
        # Use custom thresholds if provided, otherwise use defaults
        thresh_temp = custom_thresholds.get('temp', THRESH_TEMP) if custom_thresholds else THRESH_TEMP
        thresh_humid = custom_thresholds.get('humid', THRESH_HUMID) if custom_thresholds else THRESH_HUMID
        thresh_wind = custom_thresholds.get('wind', THRESH_WIND) if custom_thresholds else THRESH_WIND
        thresh_gusts = custom_thresholds.get('gusts', THRESH_GUSTS) if custom_thresholds else THRESH_GUSTS
        thresh_soil_moist = custom_thresholds.get('soil', THRESH_SOIL_MOIST) if custom_thresholds else THRESH_SOIL_MOIST
        
        # Convert temperature threshold from Fahrenheit to Celsius for internal use
        thresh_temp_celsius = (thresh_temp - 32) * 5/9
        
        # Ensure we have valid values by providing defaults if values are None
        air_temp = weather_data.get("air_temp")
        relative_humidity = weather_data.get("relative_humidity")
        wind_speed = weather_data.get("wind_speed")
        wind_gust = weather_data.get("wind_gust")
        soil_moisture_15cm = weather_data.get("soil_moisture_15cm")
        
        # Check if we're using any cached data
        cached_fields = weather_data.get('cached_fields', {})
        using_cached_data = any(cached_fields.values()) if cached_fields else False
        
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
        temp_exceeded = temp > thresh_temp_celsius
        humidity_exceeded = humidity < thresh_humid
        wind_exceeded = wind > thresh_wind
        gusts_exceeded = gusts > thresh_gusts
        soil_exceeded = soil < thresh_soil_moist
        
        # Log threshold checks
        logger.info(f"Threshold checks: temp={temp_exceeded}, humidity={humidity_exceeded}, "
                    f"wind={wind_exceeded}, gusts={gusts_exceeded}, soil={soil_exceeded}")
        
        # If all thresholds are exceeded: RED, otherwise: ORANGE
        if temp_exceeded and humidity_exceeded and wind_exceeded and gusts_exceeded and soil_exceeded:
            risk = "Red"
            explanation = "High fire risk due to high temperature, low humidity, strong winds, high wind gusts, and low soil moisture."
        else:
            risk = "Orange"
            explanation = "Low or Moderate Fire Risk. Exercise standard prevention practices."
        
        # Add notice if using cached data
        if using_cached_data:
            explanation = f"NOTICE: Displaying cached data. {explanation}"
            
        return risk, explanation

    except Exception as e:
        logger.error(f"Error calculating fire risk: {str(e)}")
        return "Error", f"Could not calculate risk: {str(e)}"

# New endpoint for simulation
@app.post("/simulate-fire-risk")
async def simulate_fire_risk(request: Request, thresholds: Dict[str, float]):
    # Validate input (add more validation as needed)
    if not thresholds:
        raise HTTPException(status_code=400, detail="Missing threshold values")

    # Use data from cache or fetch if not available
    if data_cache.fire_risk_data is None:
        await refresh_data_cache(BackgroundTasks())

    if data_cache.fire_risk_data is None:
        raise HTTPException(status_code=503, detail="Weather data not available. Please try again later.")

    weather_data = data_cache.fire_risk_data.get("weather")
    if weather_data is None:
        raise HTTPException(status_code=503, detail="Weather data not available. Please try again later.")

    # Apply custom thresholds to weather data before calculating risk
    modified_weather_data = weather_data.copy()
    modified_weather_data.update({key: thresholds[key] for key in thresholds if key in weather_data})

    # Calculate fire risk using custom thresholds
    simulated_risk, explanation = calculate_fire_risk(modified_weather_data, custom_thresholds=thresholds)

    return {"risk": simulated_risk, "explanation": explanation}



@app.get("/check-env")
@dev_only_endpoint
async def check_env():
    """Check if Render environment variables are available.

    This endpoint is only available in development mode for security reasons.
    """
    synoptic_key = os.getenv("SYNOPTICDATA_API_KEY")
    wunderground_key = os.getenv("WUNDERGROUND_API_KEY")
    return {
        "SYNOPTICDATA_API_KEY": synoptic_key if synoptic_key else "MISSING",
        "WUNDERGROUND_API_KEY": wunderground_key if wunderground_key else "MISSING"
    }


@app.get("/test-api")
@dev_only_endpoint
async def test_api():
    """Test if Render can reach Synoptic API. This endpoint is only available in development mode."""
    try:
        response = requests.get("https://api.synopticdata.com/v2/stations/latest")
        return {"status": response.status_code, "response": response.text[:500]}
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


@app.get("/test-synoptic-auth")
@dev_only_endpoint
async def test_synoptic_auth():
    """Test the Synoptic API authentication flow to diagnose 401 errors."""
    url = f"{SYNOPTIC_BASE_URL}/stations/latest?token={SYNOPTIC_API_KEY}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return {"status": "success", "message": "Synoptic API authentication successful"}
    except requests.exceptions.HTTPError as http_err:
        return {"status": "error", "message": f"HTTP Error: {http_err}", "response_text": response.text}
    except requests.exceptions.RequestException as err:
        return {"status": "error", "message": f"An error occurred: {err}"}


@app.get("/test-cache-system", response_class=HTMLResponse)
@dev_only_endpoint
async def test_cache_system(request: Request):
    """A visual interface for testing the cache system"""
    # ... existing implementation


@app.get("/force-cached-mode", response_class=HTMLResponse)
@dev_only_endpoint
async def force_cached_mode(request: Request):
    """Force the system to display cached data."""
    # ... existing implementation


@app.get("/reset-cached-mode", response_class=HTMLResponse)
@dev_only_endpoint
async def reset_cached_mode(background_tasks: BackgroundTasks, request: Request):
    """Reset the system from cached data mode back to normal operations."""
    # ... existing implementation


@app.get("/test-partial-failure", response_class=HTMLResponse)
@dev_only_endpoint
async def test_partial_failure(request: Request):
    """Test endpoint that simulates a partial API failure."""
    # ... existing implementation


# --- other endpoints ---

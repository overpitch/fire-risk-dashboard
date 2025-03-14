from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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
from typing import Dict, Any, Optional, Callable
import pytz
import functools

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
        """Check if the data is stale (older than max_age_minutes)"""
        if self.last_updated is None:
            return True
        # Use timezone-aware comparison
        pacific_tz = pytz.timezone('America/Los_Angeles')
        now = datetime.now(pacific_tz)
        age = now - self.last_updated
        return age > timedelta(minutes=max_age_minutes)
    
    def is_critically_stale(self) -> bool:
        """Check if the data is critically stale (older than data_timeout_threshold)"""
        if self.last_updated is None:
            return True
        # Use timezone-aware comparison
        pacific_tz = pytz.timezone('America/Los_Angeles')
        now = datetime.now(pacific_tz)
        age = now - self.last_updated
        return age > timedelta(minutes=self.data_timeout_threshold)
    
    def update_cache(self, synoptic_data, wunderground_data, fire_risk_data):
        """Update the cache with new data"""
        # Create timezone-aware datetime for Pacific timezone
        pacific_tz = pytz.timezone('America/Los_Angeles')
        current_time = datetime.now(pacific_tz)
        
        with self._lock:
            self.synoptic_data = synoptic_data
            self.wunderground_data = wunderground_data
            self.fire_risk_data = fire_risk_data
            self.last_updated = current_time
            self.last_update_success = True
            
            # Reset all cached field flags
            for field in self.cached_fields:
                self.cached_fields[field] = False
            self.using_cached_data = False
            
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

@app.get("/test-api")
@dev_only_endpoint
async def test_api():
    """Test if Render can reach Synoptic API.
    
    This endpoint is only available in development mode.
    """
    try:
        response = requests.get("https://api.synopticdata.com/v2/stations/latest")
        return {"status": response.status_code, "response": response.text[:500]}
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}

@app.get("/test-synoptic-auth")
@dev_only_endpoint
async def test_synoptic_auth():
    """Test the Synoptic API authentication flow to diagnose 401 errors."""
    results = {}
    
    # Step 1: Get the API key from environment
    api_key = os.getenv("SYNOPTICDATA_API_KEY")
    if not api_key:
        return {"error": "API key not found in environment variables"}
    
    results["api_key_masked"] = f"{api_key[:5]}...{api_key[-3:]}"
    
    try:
        # Step 2: Get a token
        token_url = f"{SYNOPTIC_BASE_URL}/auth?apikey={api_key}"
        token_response = requests.get(token_url)
        token_data = token_response.json()
        
        results["token_request"] = {
            "url": f"{SYNOPTIC_BASE_URL}/auth?apikey=MASKED",
            "status_code": token_response.status_code,
            "response": token_data
        }
        
        if token_response.status_code != 200 or "TOKEN" not in token_data:
            return results
        
        token = token_data.get("TOKEN")
        results["token_masked"] = f"{token[:5]}...{token[-3:]}" if token else None
        
        # Step 3: Test the token with a simple request
        station_ids = f"{SOIL_MOISTURE_STATION_ID},{WEATHER_STATION_ID}"
        data_url = f"{SYNOPTIC_BASE_URL}/stations/latest?stid={station_ids}&token={token}"
        data_response = requests.get(data_url)
        
        # Try to parse the response as JSON
        try:
            data_json = data_response.json()
            # Limit the size of the response for display
            if "STATION" in data_json and isinstance(data_json["STATION"], list):
                # Just show station IDs instead of full data
                station_ids = [station.get("STID") for station in data_json["STATION"]]
                data_json["STATION"] = f"Found {len(station_ids)} stations: {', '.join(station_ids)}"
        except:
            data_json = {"error": "Could not parse JSON response"}
        
        results["data_request"] = {
            "url": f"{SYNOPTIC_BASE_URL}/stations/latest?stid={station_ids}&token=MASKED",
            "status_code": data_response.status_code,
            "response_preview": data_json
        }
        
        # Step 4: Test each station individually to see if any specific one is causing issues
        for station_id in [SOIL_MOISTURE_STATION_ID, WEATHER_STATION_ID]:
            single_url = f"{SYNOPTIC_BASE_URL}/stations/latest?stid={station_id}&token={token}"
            single_response = requests.get(single_url)
            
            try:
                single_json = single_response.json()
                # Simplify the response for display
                if "STATION" in single_json and isinstance(single_json["STATION"], list):
                    single_json["STATION"] = f"Found {len(single_json['STATION'])} stations"
            except:
                single_json = {"error": "Could not parse JSON response"}
            
            results[f"station_{station_id}_request"] = {
                "status_code": single_response.status_code,
                "success": single_response.status_code == 200
            }
        
        return results
        
    except requests.exceptions.RequestException as e:
        results["error"] = str(e)
        return results

@app.get("/test-cache-system", response_class=HTMLResponse)
@dev_only_endpoint
async def test_cache_system():
    """A visual interface for testing the cache system"""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cache System Test</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            padding: 30px;
            font-family: Arial, sans-serif;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
        }
        h1 {
            margin-bottom: 20px;
        }
        .step {
            margin-bottom: 15px;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 5px;
        }
        .btn-primary, .btn-success {
            margin-right: 10px;
            margin-bottom: 10px;
        }
        .footer {
            margin-top: 30px;
            border-top: 1px solid #eee;
            padding-top: 20px;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Test the Data Caching System</h1>
        
        <div class="alert alert-info">
            <p>This page lets you test how the system handles API failures by displaying cached data.</p>
        </div>
        
        <div class="step">
            <h4>Step 1: View the normal dashboard</h4>
            <p>First, view the <a href="/" target="_blank">dashboard</a> with regular live data.</p>
        </div>
        
        <div class="step">
            <h4>Step 2: Simulate API failure</h4>
            <p>Click the button below to simulate an API failure. This will:</p>
            <ul>
                <li>Temporarily disable the API keys</li>
                <li>Force the system to use cached data</li>
            </ul>
            <style>
                /* Custom button styles to ensure consistent height across browsers */
                .test-button {
                    display: inline-block;
                    height: 40px;
                    line-height: 26px;
                    padding: 6px 16px;
                    margin-right: 10px;
                    margin-bottom: 10px;
                    text-align: center;
                    white-space: nowrap;
                    vertical-align: middle;
                    border-radius: 4px;
                    font-weight: 400;
                    font-size: 16px;
                    text-decoration: none;
                }
                .test-button-primary {
                    background-color: #0d6efd;
                    border: 1px solid #0d6efd;
                    color: white;
                }
                .test-button-warning {
                    background-color: #ffc107;
                    border: 1px solid #ffc107;
                    color: black;
                }
                .test-button:hover {
                    opacity: 0.9;
                }
            </style>
            <div style="display: flex;">
                <a href="/force-cached-mode" class="test-button test-button-primary">Simulate Complete API Failure</a>
                <a href="/test-partial-failure" class="test-button test-button-warning">Simulate Partial API Failure</a>
            </div>
        </div>
        
        <div class="step">
            <h4>Step 3: View the dashboard with cached data</h4>
            <p>After clicking the button above, go to the dashboard to see the cached data display:</p>
            <a href="/" class="btn btn-primary">View Dashboard with Cached Data</a>
            <p>Note how the cached data is visually distinct, with warning banners and a different background color.</p>
        </div>
        
        <div class="step">
            <h4>Step 4: Reset the system to normal operation</h4>
            <p>When you want to return to normal operation, click the reset button:</p>
            <a href="/reset-cached-mode" class="btn btn-success">Reset to Normal Operation</a>
            <p>This will restore the original API keys and make fresh API calls.</p>
        </div>
        
        <div class="footer">
            <p><a href="/">Return to Dashboard</a></p>
        </div>
    </div>
</body>
</html>"""

@app.get("/force-cached-mode", response_class=HTMLResponse)
@dev_only_endpoint
async def force_cached_mode():
    """Force the system to display cached data.
    
    This is a simpler approach than temporarily disabling API keys:
    1. Ensures there's valid cached data available
    2. Directly sets the system to use cached data
    3. Redirects to the dashboard to show the cached data
    """
    # Make sure we have cached data first
    if data_cache.last_valid_data["timestamp"] is None:
        return """
        <html>
        <head>
            <title>Error: No Cached Data</title>
            <style>
                body { font-family: Arial; padding: 20px; text-align: center; }
                .error { color: red; border: 1px solid red; padding: 10px; }
            </style>
        </head>
        <body>
            <h1>Error: No Cached Data Available</h1>
            <div class="error">
                <p>There is no cached data available yet. Please visit the dashboard first to populate the cache.</p>
            </div>
            <p><a href="/">Return to dashboard</a></p>
        </body>
        </html>
        """
    
    # Set the flag to use cached data
    data_cache.using_cached_data = True
    logger.info("🔵 TEST MODE: Forced cached data display")
    
    # Get timestamp information for display
    pacific_tz = pytz.timezone('America/Los_Angeles')
    current_time = datetime.now(pacific_tz)
    cached_time = data_cache.last_valid_data["timestamp"]
    
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
    
    # Update the cached fire risk data
    if data_cache.fire_risk_data:
        cached_fire_risk_data = data_cache.last_valid_data["fire_risk_data"].copy()
        cached_fire_risk_data["cached_data"] = {
            "is_cached": True,
            "original_timestamp": cached_time.isoformat(),
            "age": age_str
        }
        
        # Add or update the explanation with cache notice
        original_explanation = cached_fire_risk_data.get("explanation", "")
        if "cached data" not in original_explanation.lower():
            cached_fire_risk_data["explanation"] = f"{original_explanation} NOTICE: Displaying cached data from {cached_time.strftime('%Y-%m-%d %H:%M')} ({age_str} old)."
        
        # Update the cache
        data_cache.fire_risk_data = cached_fire_risk_data
    
    # Redirect to home page with success message
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/", status_code=303)

@app.get("/reset-cached-mode", response_class=HTMLResponse)
@dev_only_endpoint
async def reset_cached_mode(background_tasks: BackgroundTasks):
    """Reset the system from cached data mode back to normal operations
    
    This endpoint:
    1. Clears the using_cached_data flag
    2. Resets any cached data modifications
    3. Forces a fresh data refresh
    4. Returns a simple page confirming the reset
    """
    # Clear the cached data flag
    data_cache.using_cached_data = False
    
    # Reset the fire risk data to remove any cached data indicators
    if data_cache.fire_risk_data and "cached_data" in data_cache.fire_risk_data:
        # Remove the cached_data field
        fire_risk_copy = data_cache.fire_risk_data.copy()
        del fire_risk_copy["cached_data"]
        
        # Remove any cached data mentions from the explanation
        if "explanation" in fire_risk_copy:
            explanation = fire_risk_copy["explanation"]
            if "NOTICE: Displaying cached data" in explanation:
                explanation = explanation.split(" NOTICE: Displaying cached data")[0]
                fire_risk_copy["explanation"] = explanation
                
        # Update the fire risk data
        data_cache.fire_risk_data = fire_risk_copy
    
    # Force a refresh with fresh data
    logger.info("Resetting from cached mode to normal operations...")
    refresh_success = await refresh_data_cache(background_tasks, force=True)
    
    status = "success" if refresh_success else "failed"
    
    # Return a simple HTML page with a JavaScript redirect
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="3;url=/">
    <title>System Reset</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 2rem;
            text-align: center;
        }}
        .success {{ color: green; }}
        .error {{ color: red; }}
    </style>
</head>
<body>
    <h1>System Reset {status.upper()}</h1>
    <div class="{status}">
        <p>The system has been reset to normal operations.</p>
        <p>Data refresh status: {status}</p>
    </div>
    <p>You will be redirected to the dashboard in 3 seconds...</p>
    <p>Or <a href="/">click here</a> to go to the dashboard now.</p>
</body>
</html>"""

@app.get("/test-partial-failure", response_class=HTMLResponse)
@dev_only_endpoint
async def test_partial_failure(background_tasks: BackgroundTasks):
    """Test endpoint that simulates a partial API failure.
    
    This endpoint will:
    1. Store original data from both APIs
    2. Deliberately remove certain fields from the data to simulate partial failure
    3. Force a refresh that will use cached values only for missing fields
    4. Show how individual fields can fall back to cached data
    """
    # First, ensure we have valid data in the cache
    if data_cache.fire_risk_data is None:
        await refresh_data_cache(background_tasks, force=True)
        if data_cache.fire_risk_data is None:
            return """
            <html>
            <head><title>Error</title></head>
            <body>
                <h1>Error: No Data Available</h1>
                <p>There is no data in the cache yet. Please visit the dashboard first.</p>
            </body>
            </html>
            """
    
    # Get the current data
    weather_data = {}
    if "weather" in data_cache.fire_risk_data:
        weather_data = data_cache.fire_risk_data["weather"].copy()
    
    # Create a modified version of the data with some fields missing
    # This simulates a partial API failure where only some fields are unavailable
    modified_weather_data = weather_data.copy()
    
    # Remove temperature and soil moisture to simulate those specific fields failing
    modified_weather_data["air_temp"] = None
    modified_weather_data["soil_moisture_15cm"] = None
    
    # Set the modified data in a way that will trigger our field-level caching
    logger.info("🧪 TEST MODE: Simulating partial API failure (temperature and soil moisture)")
    data_cache.fire_risk_data["weather"] = modified_weather_data
    
    # Force a refresh, which should only use cached data for the missing fields
    await refresh_data_cache(background_tasks, force=True)
    
    # Store information about which fields have been simulated as failing
    failed_fields = ["temperature", "soil_moisture"]
    
    # Create a custom HTML response that clearly shows some fields as cached and others as fresh
    thirty_min_ago = (datetime.now(pytz.timezone('America/Los_Angeles')) - timedelta(minutes=30)).strftime('%I:%M %p')
    
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Field-Level Caching Demo</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            font-family: Arial, sans-serif;
            padding: 30px;
        }
        .header {
            background-color: #003366;
            color: white;
            padding: 15px;
            margin-bottom: 20px;
        }
        .cached-field {
            background-color: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 10px 15px;
            margin-bottom: 10px;
            position: relative;
        }
        .fresh-field {
            background-color: #d4edda;
            border-left: 4px solid #28a745;
            padding: 10px 15px;
            margin-bottom: 10px;
        }
        .badge-cached {
            position: absolute;
            right: 10px;
        }
        .badge-fresh {
            position: absolute;
            right: 10px;
        }
        .warning-banner {
            background-color: #fff3cd;
            border: 2px dashed #ffc107;
            border-left: 10px solid #ffc107;
            padding: 15px;
            margin-bottom: 20px;
        }
        .field-label {
            font-weight: bold;
            margin-right: 10px;
        }
        .field-value {
            display: inline-block;
        }
        .age-info {
            font-style: italic;
            color: #856404;
            font-size: 0.9em;
            margin-top: 5px;
        }
        .risk-banner {
            background-color: #ffc107;
            padding: 15px;
            margin-bottom: 20px;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>Sierra City Fire Weather Advisory</h2>
        </div>
        
        <div class="warning-banner">
            <h5>⚠️ Partial API Failure Detected</h5>
            <p>Some data sources are currently unavailable. The system is showing a mix of fresh and cached data.</p>
            <p>Fields marked with a <span class="badge bg-warning text-dark">CACHED</span> tag are using previously stored data.</p>
            <p>Fields marked with a <span class="badge bg-success text-white">FRESH</span> tag are using current data.</p>
        </div>
        
        <div class="risk-banner">
            <h4>Fire Risk: Orange - Low or Moderate Fire Risk. Exercise standard prevention practices.</h4>
        </div>
        
        <h3 class="mt-4 mb-3">Current Weather Conditions:</h3>
        
        <div class="cached-field">
            <span class="field-label">Temperature:</span>
            <span class="field-value">33°F</span>
            <span class="badge bg-warning text-dark badge-cached">CACHED</span>
            <div class="age-info">Data from """ + thirty_min_ago + """ (30 minutes old)</div>
        </div>
        
        <div class="fresh-field">
            <span class="field-label">Humidity:</span>
            <span class="field-value">93%</span>
            <span class="badge bg-success text-white badge-fresh">FRESH</span>
        </div>
        
        <div class="fresh-field">
            <span class="field-label">Wind Speed:</span>
            <span class="field-value">0 mph</span>
            <span class="badge bg-success text-white badge-fresh">FRESH</span>
        </div>
        
        <div class="fresh-field">
            <span class="field-label">Wind Gusts:</span>
            <span class="field-value">&lt;unavailable&gt;</span>
            <span class="badge bg-success text-white badge-fresh">FRESH</span>
        </div>
        
        <div class="cached-field">
            <span class="field-label">Soil Moisture (15cm depth):</span>
            <span class="field-value">22%</span>
            <span class="badge bg-warning text-dark badge-cached">CACHED</span>
            <div class="age-info">Data from """ + thirty_min_ago + """ (30 minutes old)</div>
        </div>
        
        <div class="alert alert-primary mt-4">
            <p>This is a demonstration of how the system handles a partial API failure. In a real scenario:</p>
            <ul>
                <li>The system automatically uses cached data for fields that fail to update</li>
                <li>Each field's freshness is evaluated independently</li>
                <li>Users can clearly see which data is current and which is from cache</li>
            </ul>
        </div>
        
        <div class="mt-5">
            <a href="/" class="btn btn-primary">Return to Live Dashboard</a>
            <a href="/test-cache-system" class="btn btn-outline-secondary ms-2">Return to Cache Testing Page</a>
        </div>
    </div>
</body>
</html>
"""

@app.get("/synoptic-api-test", response_class=HTMLResponse)
@dev_only_endpoint
async def synoptic_api_test():
    """Serve the Synoptic API testing tool."""
    with open("synoptic-api-test.html", "r") as file:
        return file.read()

@app.get("/debug-info")
@dev_only_endpoint
async def debug_info():
    """Debug endpoint to check Python version and installed packages."""
    python_version = sys.version

    # Log Python version for debugging
    logger.info(f"DEBUG CHECK: Running with Python version {python_version}")

    try:
        installed_packages = {pkg.metadata["Name"]: pkg.version for pkg in importlib.metadata.distributions()}
    except Exception as e:
        installed_packages = {"error": str(e)}

    return {
        "python_version": python_version,
        "installed_packages": installed_packages
    }

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
                
            # If all individual fields are missing and we have no cache for them, that's a problem
            if air_temp is None and relative_humidity is None and wind_speed is None and soil_moisture_15cm is None and wind_gust is None:
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
                    pacific_tz = pytz.timezone('America/Los_Angeles')
                    current_time = datetime.now(pacific_tz)
                    
                    # Calculate how old the data is for display
                    cached_time = data_cache.last_valid_data["timestamp"]
                    age_delta = current_time - cached_time
                    
                    # Format as days, hours, or minutes depending on age
                    if age_delta.days > 0:
                        age_str = f"{age_delta.days} day{'s' if age_delta.days != 1 else ''}"
                    elif age_delta.seconds // 3600 > 0:
                        hours = age_delta.seconds // 3600
                        age_str = f"{hours} hour{'s' if hours != 1 else ''}"
                    else:
                        minutes = age_delta.seconds // 60
                        age_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
                    
                    # Update the cached data to indicate it's not current
                    cached_fire_risk_data["cached_data"] = {
                        "is_cached": True,
                        "original_timestamp": cached_time.isoformat(),
                        "age": age_str
                    }
                    
                    # If the explanation doesn't already mention it, add a note about using cached data
                    if "cached data" not in cached_fire_risk_data["explanation"].lower():
                        cached_fire_risk_data["explanation"] += f" NOTICE: Displaying cached data from {cached_time.strftime('%Y-%m-%d %H:%M')} ({age_str} old)."
                    
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
            
            # Process the live data normally
            risk, explanation = calculate_fire_risk(latest_weather)
            
            # If we had data issues, add a note to the explanation
            if data_issues:
                explanation += " Note: Some data sources were unavailable."
            
            fire_risk_data = {"risk": risk, "explanation": explanation, "weather": latest_weather}
            
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

@app.get("/fire-risk")
async def fire_risk(background_tasks: BackgroundTasks, wait_for_fresh: bool = False):
    """API endpoint to fetch fire risk status.
    
    Args:
        background_tasks: FastAPI BackgroundTasks for scheduling refreshes
        wait_for_fresh: If True, wait for fresh data instead of returning stale data
    """
    # First-time fetch (cache empty)
    if data_cache.fire_risk_data is None:
        logger.info("Initial data fetch (cache empty)")
        await refresh_data_cache()
        
        # If still no data after refresh, we have a problem
        if data_cache.fire_risk_data is None:
            logger.error("No data available in cache after refresh attempt")
            raise HTTPException(
                status_code=503,
                detail="Weather data service unavailable. Please try again later."
            )
    
    # Check if data is stale
    is_stale = data_cache.is_stale(max_age_minutes=10)
    refresh_in_progress = data_cache.update_in_progress
    
    # Handle stale data
    if is_stale:
        # If requested to wait for fresh data or if data is critically stale
        if wait_for_fresh or data_cache.is_critically_stale():
            logger.info("Waiting for fresh data...")
            
            # If no refresh is in progress, start one
            if not refresh_in_progress:
                # Reset the update event and start a refresh
                data_cache.reset_update_event()
                refresh_task = asyncio.create_task(refresh_data_cache(background_tasks, force=True))
            
            # Wait for the update to complete with timeout
            success = await data_cache.wait_for_update()
            
            if not success:
                logger.warning("Timeout waiting for fresh data, returning potentially stale data")
        else:
            # Schedule background refresh if not already in progress
            if not refresh_in_progress:
                logger.info("Cache is stale. Scheduling background refresh.")
                background_tasks.add_task(refresh_data_cache, background_tasks)
    
    # If we get here, we have some data to return (potentially stale)
    # Add cache information to the response
    result = data_cache.fire_risk_data.copy()
    result["cache_info"] = {
        # The isoformat() will include timezone info for timezone-aware datetimes
        "last_updated": data_cache.last_updated.isoformat() if data_cache.last_updated else None,
        "is_fresh": not data_cache.is_stale(max_age_minutes=10),
        "refresh_in_progress": data_cache.update_in_progress,
        "using_cached_data": data_cache.using_cached_data
    }
    
    # Add field-level caching information to the response
    # If we're using cached data from a previous successful API call (fallback mode)
    if data_cache.using_cached_data:
        # Add field-specific cache information
        pacific_tz = pytz.timezone('America/Los_Angeles')
        current_time = datetime.now(pacific_tz)
        
        # Calculate how old the data is
        if data_cache.last_valid_data["timestamp"]:
            cached_time = data_cache.last_valid_data["timestamp"]
            age_delta = current_time - cached_time
            
            # Format age as days, hours, or minutes
            if age_delta.days > 0:
                age_str = f"{age_delta.days} day{'s' if age_delta.days != 1 else ''}"
            elif age_delta.seconds // 3600 > 0:
                hours = age_delta.seconds // 3600
                age_str = f"{hours} hour{'s' if hours != 1 else ''}"
            else:
                minutes = age_delta.seconds // 60
                age_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
            
            result["cached_data"] = {
                "is_cached": True,
                "original_timestamp": cached_time.isoformat(),
                "age": age_str
            }
    
    return result

# Create a lifespan context manager for application startup and shutdown
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    """Lifespan context manager for application startup and shutdown."""
    # Startup event
    logger.info("🚀 Application startup: Initializing data cache...")
    
    # Try to fetch initial data, but don't block startup if it fails
    try:
        await refresh_data_cache()
        logger.info("✅ Initial data cache populated successfully")
    except Exception as e:
        logger.error(f"❌ Failed to populate initial data cache: {str(e)}")
        logger.info("Application will continue startup and retry data fetch on first request")
    
    # Yield control back to FastAPI during application lifetime
    yield
    
    # Shutdown event (if needed in the future)
    logger.info("🛑 Application shutting down...")

# Register the lifespan context manager with FastAPI
app.router.lifespan_context = lifespan

@app.get("/", response_class=HTMLResponse)
def home():
    """Fire Risk Dashboard with Synoptic Data Attribution and Dynamic Timestamp"""
    return """<!DOCTYPE html>
<html lang='en'>
<head>
    <meta charset='UTF-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>Sierra City Fire Risk Dashboard</title>
    
    <!-- Simple red square favicon that should work in Safari -->
    <link rel="icon" href="/static/favicon.png" type="image/png">
    <link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css' rel='stylesheet'>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <link href='/static/synoptic-logo.css' rel='stylesheet'>
    <style>
        .attribution-container {
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid #ddd;
            font-size: 0.9rem;
        }
        .data-source {
            margin-bottom: 0.5rem;
        }
        .info-icon {
            cursor: pointer;
            color: #0d6efd;
            font-weight: bold;
            padding: 0 5px;
            border-radius: 50%;
            font-size: 0.8rem;
        }
        .info-icon:hover {
            text-decoration: none;
            color: #0a58ca;
        }
        .unavailable {
            background-color: #ffff99;
            padding: 0 4px;
            border-radius: 3px;
            font-style: italic;
        }
        .cache-info {
            font-size: 0.85rem;
            color: #6c757d;
            margin-bottom: 0.5rem;
        }
        .cache-fresh {
            color: #198754;
        }
        .cache-stale {
            color: #fd7e14;
        }
        #refresh-btn {
            margin-left: 10px;
            padding: 3px 10px;
            font-size: 0.9rem;
        }
        /* Style for cached data display */
        .cached-data-banner {
            background-color: #fff3cd;
            border: 2px dashed #ffc107;
            border-left: 10px solid #ffc107;
            padding: 10px 15px;
            margin-bottom: 15px;
            font-weight: bold;
            color: #856404;
        }
        .cached-data-content {
            background-color: #fff8e6;
            border: 1px solid #ffeeba;
            padding: 15px;
        }
    </style>
    <script>
        // Configure client-side settings
        const settings = {
            refreshInterval: 300000, // 5 minutes
            maxRetries: 3,
            retryDelay: 2000, // 2 seconds
            waitForFreshTimeout: 15000 // 15 seconds
        };
        
        async function fetchWithTimeout(url, options, timeout) {
            const controller = new AbortController();
            const id = setTimeout(() => controller.abort(), timeout);
            
            try {
                const response = await fetch(url, {
                    ...options,
                    signal: controller.signal
                });
                clearTimeout(id);
                return response;
            } catch (error) {
                clearTimeout(id);
                throw error;
            }
        }
            
        async function fetchFireRisk(showSpinner = false, waitForFresh = false) {
            // Show loading state if requested (for manual refresh)
            if (showSpinner) {
                document.getElementById('refresh-btn').innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Refreshing...';
                document.getElementById('refresh-btn').disabled = true;
            }
            
            let retries = 0;
            let success = false;
            let data;
            
            while (!success && retries < settings.maxRetries) {
                try {
                    // Add wait_for_fresh parameter if specified
                    const apiUrl = waitForFresh ?
                        '/fire-risk?wait_for_fresh=true' :
                        '/fire-risk';
                    
                    // Use timeout to prevent indefinite waiting
                    const timeout = waitForFresh ?
                        settings.waitForFreshTimeout :
                        10000; // 10 seconds for normal requests
                    
                    const response = await fetchWithTimeout(apiUrl, {}, timeout);
                    
                    if (!response.ok) {
                        throw new Error(`HTTP error ${response.status}`);
                    }
                    
                    data = await response.json();
                    success = true;
                    
                } catch (error) {
                    retries++;
                    console.error(`Error fetching data (attempt ${retries}/${settings.maxRetries}):`, error);
                    
                    if (retries < settings.maxRetries) {
                        // Add exponential backoff for retries
                        const delay = settings.retryDelay * Math.pow(2, retries - 1);
                        await new Promise(resolve => setTimeout(resolve, delay));
                    }
                }
            }
            
            if (!success) {
                // All retries failed
                if (showSpinner) {
                    document.getElementById('refresh-btn').innerHTML = 'Refresh Failed - Try Again';
                    document.getElementById('refresh-btn').disabled = false;
                }
                return false;
            }
            
            try {
                // Update the UI with the fetched data
                const riskDiv = document.getElementById('fire-risk');
                const weatherDetails = document.getElementById('weather-details');
                const timestampDiv = document.getElementById('timestamp');
                const cacheInfoDiv = document.getElementById('cache-info');

                // Update fire risk text with special styling for cached data
                if (data.cached_data && data.cached_data.is_cached) {
                    // Add visual styling to show cached data
                    const originalTime = new Date(data.cached_data.original_timestamp);
                    const formattedDate = originalTime.toLocaleDateString();
                    const formattedTime = originalTime.toLocaleTimeString();
                    const ageStr = data.cached_data.age;
                    
                    riskDiv.innerHTML = `
                        <div class="cached-data-banner">
                            ⚠️ NOTICE: Using cached data from ${formattedDate} at ${formattedTime} (${ageStr} old)
                        </div>
                        <div class="cached-data-content">
                            Fire Risk: ${data.risk} - ${data.explanation}
                        </div>
                    `;
                } else {
                    // Regular display for current data
                    riskDiv.innerText = `Fire Risk: ${data.risk} - ${data.explanation}`;
                }
                
                // Update cache information
                if (data.cache_info) {
                    // Parse the ISO string with timezone info
                    const lastUpdated = new Date(data.cache_info.last_updated);
                    const isFresh = data.cache_info.is_fresh;
                    const refreshInProgress = data.cache_info.refresh_in_progress;
                    const usingCachedData = data.cache_info.using_cached_data;
                    
                    let cacheClass = isFresh ? 'cache-fresh' : 'cache-stale';
                    let statusText = isFresh ? '✓ Data is fresh' : '⚠ Data may be stale';
                    
                    // If using cached data, update status text
                    if (usingCachedData) {
                        cacheClass = 'cache-stale';
                        statusText = '⚠ Using cached data - current data unavailable';
                    }
                    
                    // Extract timezone abbreviation from timestamp
                    // This will properly display the timezone from the server
                    const timeZoneAbbr = (() => {
                        // The timestamp from the server now includes timezone info
                        // We can get the timezone offset directly from the parsed date
                        const offset = lastUpdated.getTimezoneOffset();
                        const offsetHours = Math.abs(Math.floor(offset / 60));
                        
                        // Check if we're in DST based on timezone offset
                        const jan = new Date(lastUpdated.getFullYear(), 0, 1).getTimezoneOffset();
                        const jul = new Date(lastUpdated.getFullYear(), 6, 1).getTimezoneOffset();
                        const isDST = offset < Math.max(jan, jul);
                        
                        // For Pacific Time
                        if (offset >= 420 && offset <= 480) { // -7 or -8 hours
                            return isDST ? 'PDT' : 'PST';
                        }
                        return `GMT${offset <= 0 ? '+' : '-'}${offsetHours}`;
                    })();
                    
                    if (refreshInProgress) {
                        statusText += ' (refresh in progress...)';
                    }
                    
                    cacheInfoDiv.innerHTML = `
                        <span class="${cacheClass}">
                            ${statusText}
                            (Last updated: ${lastUpdated.toLocaleTimeString()} ${timeZoneAbbr})
                        </span>`;
                }

                // Set appropriate background color based on risk level
                const riskLevel = data.risk;
                let bgClass = 'bg-secondary';  // Default for unknown/error risk

                if (riskLevel === 'Red') {
                    bgClass = 'bg-danger text-white'; // Red: Danger
                } else if (riskLevel === 'Orange') {
                    bgClass = 'bg-warning text-dark'; // Orange: Warning
                }
                
                // Don't change the background color if we're using cached data
                // as we already have special styling for that
                if (!data.cached_data || !data.cached_data.is_cached) {
                    riskDiv.className = `alert ${bgClass} p-3`;
                } else {
                    riskDiv.className = 'alert p-0';  // Remove padding for our custom cached data display
                }

                // Update weather details
                // Convert temperature from Celsius to Fahrenheit using the formula F = (C * 9/5) + 32
                // Round all measurements to the nearest whole number
                const tempCelsius = data.weather.air_temp;
                const tempFahrenheit = tempCelsius ? Math.round((tempCelsius * 9/5) + 32) + '°F' : '<span class="unavailable">&lt;unavailable&gt;</span>';
                const soilMoisture = data.weather.soil_moisture_15cm ? Math.round(data.weather.soil_moisture_15cm) + '%' : '<span class="unavailable">&lt;unavailable&gt;</span>';
                const weatherStation = data.weather.data_sources.weather_station;
                const soilStation = data.weather.data_sources.soil_moisture_station;
                
                // Check for data issues
                const dataStatus = data.weather.data_status;
                const hasIssues = dataStatus && dataStatus.issues && dataStatus.issues.length > 0;
                
                // Build the weather details HTML
                let detailsHTML = `<h5>Current Weather Conditions:</h5>`;
                
                // If we're using cached data, add a note about the data age
                if (data.cached_data && data.cached_data.is_cached) {
                    detailsHTML += `
                    <div class="alert alert-warning p-2 small">
                        <strong>NOTE:</strong> Displaying cached weather data. Current data is unavailable.
                    </div>`;
                }
                
                // Add warning about data issues if applicable
                if (hasIssues) {
                    detailsHTML += `
                    <div class="alert alert-warning p-2 small">
                        <strong>Data Quality Warning:</strong> Some data may be missing or unavailable.<br>
                        <ul class="mb-0">
                            ${dataStatus.issues.map(issue => `<li>${issue}</li>`).join('')}
                        </ul>
                    </div>`;
                }
                
                // Handle potentially missing data with fallbacks - round all values to nearest whole number
                const humidity = data.weather.relative_humidity ? Math.round(data.weather.relative_humidity) + '%' : '<span class="unavailable">&lt;unavailable&gt;</span>';
                const windSpeed = data.weather.wind_speed !== null && data.weather.wind_speed !== undefined ? Math.round(data.weather.wind_speed) + ' mph' : '<span class="unavailable">&lt;unavailable&gt;</span>';
                const windGust = data.weather.wind_gust !== null && data.weather.wind_gust !== undefined ? Math.round(data.weather.wind_gust) + ' mph' : '<span class="unavailable">&lt;unavailable&gt;</span>';
                const windGustStation = data.weather.data_sources.wind_gust_station;
                
                // Get threshold values for color formatting
                const THRESH_TEMP = 75; // Temperature threshold in Fahrenheit
                const THRESH_HUMID = 15; // Humidity threshold in percent (below this is risky)
                const THRESH_WIND = 15;  // Wind speed threshold in mph
                const THRESH_GUSTS = 20; // Wind gust threshold in mph
                const THRESH_SOIL_MOIST = 10; // Soil moisture threshold in percent (below this is risky)
                
                // Check if values exceed thresholds for color formatting - use rounded values
                const tempValue = tempCelsius ? Math.round((tempCelsius * 9/5) + 32) : null;
                const tempExceeds = tempValue !== null && tempValue > THRESH_TEMP;
                
                const humidValue = data.weather.relative_humidity ? Math.round(data.weather.relative_humidity) : null;
                const humidExceeds = humidValue !== null && humidValue < THRESH_HUMID;
                
                const windValue = data.weather.wind_speed ? Math.round(data.weather.wind_speed) : null;
                const windExceeds = windValue !== null && windValue > THRESH_WIND;
                
                const gustValue = data.weather.wind_gust ? Math.round(data.weather.wind_gust) : null;
                const gustExceeds = gustValue !== null && gustValue > THRESH_GUSTS;
                
                const soilValue = data.weather.soil_moisture_15cm ? Math.round(data.weather.soil_moisture_15cm) : null;
                const soilExceeds = soilValue !== null && soilValue < THRESH_SOIL_MOIST;
                
                const weatherContainerClass = data.cached_data && data.cached_data.is_cached ? 'cached-data-content' : '';
                
                // Create a style for the threshold display
                const thresholdStyle = "display: inline-block; margin-left: 10px; font-size: 0.85rem; color: #6c757d; border-left: 1px solid #ddd; padding-left: 10px;";
                
                detailsHTML += `
                    <div class="${weatherContainerClass}">
                        <ul>
                            <li style="color: ${tempExceeds ? 'red' : 'black'}">
                                <span style="color: ${tempExceeds ? 'red' : 'black'}">Temperature: ${tempFahrenheit}</span>
                                <span style="${thresholdStyle}">Threshold: >${THRESH_TEMP}°F</span>
                                <span class="info-icon" data-bs-toggle="tooltip" data-bs-html="true" title="Sierra City<br>From: Synoptic Data">ⓘ</span>
                            </li>
                            <li style="color: ${humidExceeds ? 'red' : 'black'}">
                                <span style="color: ${humidExceeds ? 'red' : 'black'}">Humidity: ${humidity}</span>
                                <span style="${thresholdStyle}">Threshold: <${THRESH_HUMID}%</span>
                                <span class="info-icon" data-bs-toggle="tooltip" data-bs-html="true" title="Sierra City<br>From: Synoptic Data">ⓘ</span>
                            </li>
                            <li style="color: ${windExceeds ? 'red' : 'black'}">
                                <span style="color: ${windExceeds ? 'red' : 'black'}">Wind Speed: ${windSpeed}</span>
                                <span style="${thresholdStyle}">Threshold: >${THRESH_WIND} mph</span>
                                <span class="info-icon" data-bs-toggle="tooltip" data-bs-html="true" title="Sierra City<br>From: Synoptic Data">ⓘ</span>
                            </li>
                            <li style="color: ${gustExceeds ? 'red' : 'black'}">
                                <span style="color: ${gustExceeds ? 'red' : 'black'}">Wind Gusts: ${windGust}</span>
                                <span style="${thresholdStyle}">Threshold: >${THRESH_GUSTS} mph</span>
                                <span class="info-icon" data-bs-toggle="tooltip" data-bs-html="true" title="${windGustStation}<br>From: Wunderground">ⓘ</span>
                            </li>
                            <li style="color: ${soilExceeds ? 'red' : 'black'}">
                                <span style="color: ${soilExceeds ? 'red' : 'black'}">Soil Moisture (15cm depth): ${soilMoisture}</span>
                                <span style="${thresholdStyle}">Threshold: <${THRESH_SOIL_MOIST}%</span>
                                <span class="info-icon" data-bs-toggle="tooltip" data-bs-html="true" title="Downieville<br>From: Synoptic Data">ⓘ</span>
                            </li>
                        </ul>
                    </div>`;
                    
                weatherDetails.innerHTML = detailsHTML;
                    
                // Update timestamp and re-enable refresh button if it was used
                const now = new Date();
                
                // Get the timezone abbreviation using the same method as above
                const timeZoneAbbr = (() => {
                    const offset = now.getTimezoneOffset();
                    const offsetHours = Math.abs(Math.floor(offset / 60));
                    
                    // Check if we're in DST based on timezone offset
                    const jan = new Date(now.getFullYear(), 0, 1).getTimezoneOffset();
                    const jul = new Date(now.getFullYear(), 6, 1).getTimezoneOffset();
                    const isDST = offset < Math.max(jan, jul);
                    
                    // For Pacific Time
                    if (offset >= 420 && offset <= 480) { // -7 or -8 hours
                        return isDST ? 'PDT' : 'PST';
                    }
                    return `GMT${offset <= 0 ? '+' : '-'}${offsetHours}`;
                })();
                
                timestampDiv.innerText = `Last updated: ${now.toLocaleDateString()} at ${now.toLocaleTimeString()} ${timeZoneAbbr}`;
                
                if (showSpinner) {
                    document.getElementById('refresh-btn').innerHTML = 'Refresh Data';
                    document.getElementById('refresh-btn').disabled = false;
                }
                
                return true; // Signal success
                
            } catch (error) {
                console.error("Error fetching fire risk data:", error);
                if (showSpinner) {
                    document.getElementById('refresh-btn').innerHTML = 'Refresh Failed - Try Again';
                    document.getElementById('refresh-btn').disabled = false;
                }
                return false;
            }
        }

        // Initialize tooltips
        function initializeTooltips() {
            const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        }
        
        // Handle manual refresh button click - uses waitForFresh=true to ensure we get fresh data
        function manualRefresh() {
            // Pass true for both showSpinner and waitForFresh
            fetchFireRisk(true, true).then(success => {
                if (success !== false) {
                    initializeTooltips();
                }
            });
        }

        // Auto-refresh functionality
        function setupRefresh() {
            // Initial load without waiting for fresh data
            fetchFireRisk().then(success => {
                if (success !== false) {
                    initializeTooltips();
                }
            });
            
            // Setup auto-refresh
            setInterval(() => {
                // Don't wait for fresh data on auto-refresh, to prevent hanging the UI
                fetchFireRisk(false, false).then(success => {
                    if (success !== false) {
                        initializeTooltips();
                    }
                });
            }, settings.refreshInterval);
        }

        window.onload = setupRefresh;
    </script>
</head>
<body>
    <!-- Navigation Bar -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary" style="background-color: #003366 !important;">
        <div class="container">
            <a class="navbar-brand fw-bold" href="#">
                Sierra City Fire Weather Advisory
            </a>
            <div class="d-flex">
                <button class="btn btn-outline-light" data-bs-toggle="modal" data-bs-target="#aboutUsModal">About Us</button>
            </div>
        </div>
    </nav>
    
    <div class="container mt-5">
    
    <div class="d-flex justify-content-between align-items-center mb-2 mt-3">
        <div id="cache-info" class="cache-info">Data status: Loading...</div>
        <button id="refresh-btn" class="btn btn-sm btn-outline-primary" onclick="manualRefresh()">Refresh Data</button>
    </div>
    
    <div id='fire-risk' class='alert alert-info'>Loading fire risk data...</div>
    <div id='weather-details' class='mt-3'></div>
    
    <div class="alert mt-4 mb-4" style="background-color: #d1ecff;">
        <p>Fire weather needs to be local. A few Sierra City residents analyze local wind, humidity, temperature and soil moisture data and offer their advice in real time. This fire weather advisory is a best guess of what you should know about local fire weather conditions before there is a fire event.</p>
        
        <p>The two-stage advisory (Orange for Low or Moderate Risk, Red for Extreme Risk) is distributed via email and text each morning. Should fire weather conditions change during the course of the day, additional advisories will be issued.</p>
        
        <p class="mb-0">This fire weather advisory is not a substitute for official notifications by law enforcement or other government or private agencies.</p>
    </div>
    
    <div class="attribution-container">
        <div id="timestamp" class="timestamp">Last updated: Loading...</div>
        <div class="attribution">
            Weather observations aggregated by&nbsp;<a href="https://www.wunderground.com/" target="_blank">Weather Underground</a>&nbsp;and&nbsp;<a href="https://synopticdata.com/" target="_blank">Synoptic Data</a>
            <img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA0MDAgNDAwIiB3aWR0aD0iMTUwIiBoZWlnaHQ9IjE1MCI+CiAgPGNpcmNsZSBjeD0iMjAwIiBjeT0iMjAwIiByPSIxNDAiIGZpbGw9IiMxYTQ1OTgiIC8+CiAgPHBhdGggZD0iTTYwLDE1MCBDMTUwLDEwMCAyNTAsMTEwIDM1MCwxNTAiIHN0cm9rZT0iIzdkZDBmNSIgc3Ryb2tlLXdpZHRoPSIyNSIgZmlsbD0ibm9uZSIgLz4KICA8cGF0aCBkPSJNNjAsMjAwIEMxNTAsMTUwIDI1MCwxNjAgMzUwLDIwMCIgc3Ryb2tlPSIjN2RkMGY1IiBzdHJva2Utd2lkdGg9IjI1IiBmaWxsPSJub25lIiAvPgogIDxwYXRoIGQ9Ik02MCwyNTAgQzE1MCwyMDAgMjUwLDIxMCAzNTAsMjUwIiBzdHJva2U9IiM3ZGQwZjUiIHN0cm9rZS13aWR0aD0iMjUiIGZpbGw9Im5vbmUiIC8+Cjwvc3ZnPg==" alt="Synoptic Data" class="synoptic-logo">
        </div>
    </div>
    
    <!-- About Us Modal -->
    <div class="modal fade" id="aboutUsModal" tabindex="-1" aria-labelledby="aboutUsModalLabel" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="aboutUsModalLabel">About Us</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <p>This Fire Weather Advisory website was born from the Sierra City Community Radio1 (SCCR1) initiative. SCCR1 provides essential communication via handheld radios when power, phone, and internet services are disrupted, while also fostering stronger neighborhood connections.</p>
                    
                    <p>It was inspired by a January 2025 incident when high winds during low humidity reignited a burn pile. We realized many residents were unaware of these dangerous weather conditions. After community discussions, we developed this advisory system to keep our neighbors informed and safer.</p>
                    
                    <p>For more information about our services or to manage your notification preferences, please contact us at <a href="mailto:fredsnarf@getlost.com">fredsnarf@getlost.com</a>.</p>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                </div>
            </div>
        </div>
    </div>
    </div> <!-- Close container -->
</body>
</html>"""

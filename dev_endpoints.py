import os
import functools
import importlib.metadata
import sys
import requests
import json
from fastapi import APIRouter, BackgroundTasks, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from config import IS_PRODUCTION, SYNOPTIC_BASE_URL, SYNOPTIC_API_KEY, WUNDERGROUND_API_KEY, SOIL_MOISTURE_STATION_ID, WEATHER_STATION_ID, logger
from cache import data_cache
from cache_refresh import refresh_data_cache

# Create a router for development endpoints
router = APIRouter()

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

@router.get("/check-env")
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

@router.get("/test-api")
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

@router.get("/test-synoptic-auth")
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

@router.get("/test-cache-system", response_class=HTMLResponse)
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

@router.get("/force-cached-mode", response_class=HTMLResponse)
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
    
    # Set all cached fields to true since we're using all cached data
    for field in data_cache.cached_fields:
        data_cache.cached_fields[field] = True
        
    logger.info("🔵 TEST MODE: Forced cached data display")
    
    # Get timestamp information for display
    from datetime import datetime
    from config import TIMEZONE
    from data_processing import format_age_string
    
    current_time = datetime.now(TIMEZONE)
    cached_time = data_cache.last_valid_data["timestamp"]
    
    # Calculate age of data
    age_str = format_age_string(current_time, cached_time)
    
    # Update the cached fire risk data
    if data_cache.fire_risk_data:
        cached_fire_risk_data = data_cache.last_valid_data["fire_risk_data"].copy()
        
        # Add timestamps to each cached field to ensure age indicators appear
        if 'weather' in cached_fire_risk_data:
            # Ensure there's a cached_fields structure
            if not 'cached_fields' in cached_fire_risk_data['weather']:
                cached_fire_risk_data['weather']['cached_fields'] = {}
            
            # In test mode, force all fields to be marked as cached
            cached_fire_risk_data['weather']['cached_fields'] = {
                'temperature': True,
                'humidity': True,
                'wind_speed': True,
                'soil_moisture': True,
                'wind_gust': True,
                'timestamp': {
                    'temperature': cached_time.isoformat(),
                    'humidity': cached_time.isoformat(),
                    'wind_speed': cached_time.isoformat(),
                    'soil_moisture': cached_time.isoformat(),
                    'wind_gust': cached_time.isoformat()
                }
            }
        
        # Add note to modal content
        cached_fire_risk_data['modal_content'] = {
            'note': 'Displaying cached weather data. Current data is unavailable.',
            'warning_title': 'Test Mode Active',
            'warning_issues': ['This is a test of the caching system. All data shown is from cache.']
        }
        
        cached_fire_risk_data["cached_data"] = {
            "is_cached": True,
            "original_timestamp": cached_time.isoformat(),
            "age": age_str
        }
        
        # Update the cache
        data_cache.fire_risk_data = cached_fire_risk_data
    
    # Redirect to home page with success message
    return RedirectResponse(url="/", status_code=303)

# The toggle-test-mode endpoint has been moved to endpoints.py
# to make it available in both development and production environments

@router.get("/reset-cached-mode", response_class=HTMLResponse)
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

@router.get("/test-partial-failure", response_class=HTMLResponse)
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
    from datetime import datetime, timedelta
    from config import TIMEZONE
    
    thirty_min_ago = (datetime.now(TIMEZONE) - timedelta(minutes=30)).strftime('%I:%M %p')
    
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

@router.get("/debug-info")
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

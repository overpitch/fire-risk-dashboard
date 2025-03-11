from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import requests
import os
import logging
import sys
import importlib.metadata

# Only load .env for local development (not on Render)
if os.getenv("RENDER") is None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("Loaded .env file for local development.")
    except ImportError:
        print("python-dotenv is not installed. Skipping .env loading.")

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

@app.get("/check-env")
def check_env():
    """Check if Render environment variables are available."""
    synoptic_key = os.getenv("SYNOPTICDATA_API_KEY")
    wunderground_key = os.getenv("WUNDERGROUND_API_KEY")
    return {
        "SYNOPTICDATA_API_KEY": synoptic_key if synoptic_key else "MISSING",
        "WUNDERGROUND_API_KEY": wunderground_key if wunderground_key else "MISSING"
    }

# Fire risk thresholds from environment variables
THRESH_TEMP = float(os.getenv("THRESH_TEMP", 90))            # Temperature threshold in Fahrenheit
THRESH_HUMID = float(os.getenv("THRESH_HUMID", 15))          # Humidity threshold in percent
THRESH_WIND = float(os.getenv("THRESH_WIND", 20))            # Wind speed threshold in mph
THRESH_GUSTS = float(os.getenv("THRESH_GUSTS", 25))          # Wind gust threshold in mph
THRESH_SOIL_MOIST = float(os.getenv("THRESH_SOIL_MOIST", 5)) # Soil moisture threshold in percent

# Convert temperature threshold from Fahrenheit to Celsius for internal use
THRESH_TEMP_CELSIUS = (THRESH_TEMP - 32) * 5/9

logger.info(f"Using thresholds: TEMP={THRESH_TEMP}°F ({THRESH_TEMP_CELSIUS:.1f}°C), "
            f"HUMID={THRESH_HUMID}%, WIND={THRESH_WIND}mph, "
            f"GUSTS={THRESH_GUSTS}mph, SOIL={THRESH_SOIL_MOIST}%")

@app.get("/test-api")
def test_api():
    """Test if Render can reach Synoptic API."""
    try:
        response = requests.get("https://api.synopticdata.com/v2/stations/latest")
        return {"status": response.status_code, "response": response.text[:500]}
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}
    
@app.get("/debug-info")
def debug_info():
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

        token = token_data.get("TOKEN")  # ✅ Extract token correctly
        if token:
            logger.info(f"✅ Received API token: {token[:5]}... (truncated)")
        else:
            logger.error("🚨 Token was empty or missing in response.")

        return token

    except requests.exceptions.RequestException as e:
        logger.error(f"🚨 Error fetching API token: {e}")
        return None

def get_weather_data(location_ids):
    """Get weather data using the temporary token.
    
    Args:
        location_ids: A string of comma-separated station IDs
    """
    token = get_api_token()
    if not token:
        return None

    try:
        response = requests.get(
            f"{SYNOPTIC_BASE_URL}/stations/latest?stid={location_ids}&token={token}"
        )
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        logger.error(f"Exception during API request: {str(e)}")
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
        
        # If all thresholds are exceeded: RED, otherwise: YELLOW
        if temp_exceeded and humidity_exceeded and wind_exceeded and gusts_exceeded and soil_exceeded:
            return "Red", "High fire risk due to high temperature, low humidity, strong winds, high wind gusts, and low soil moisture."
        else:
            return "Yellow", "Moderate fire risk. Monitor conditions carefully."

    except Exception as e:
        logger.error(f"Error calculating fire risk: {str(e)}")
        return "Error", f"Could not calculate risk: {str(e)}"

@app.get("/fire-risk")
def fire_risk():
    """API endpoint to fetch fire risk status."""
    # Fetch data from Synoptic stations
    station_ids = f"{SOIL_MOISTURE_STATION_ID},{WEATHER_STATION_ID}"
    weather_data = get_weather_data(station_ids)
    
    # Fetch data from Weather Underground for wind gusts
    wunderground_data = get_wunderground_data(WUNDERGROUND_STATION_ID)
    
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
    
    if not weather_data:
        logger.error("Failed to get any weather data from API")
        data_issues.append("Failed to fetch weather data from API")
    elif "STATION" not in weather_data:
        logger.error("Weather API response missing STATION data")
        data_issues.append("Invalid response format from weather API")
    else:
        stations = weather_data["STATION"]
        
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
        }
    }

    risk, explanation = calculate_fire_risk(latest_weather)
    
    # If we had data issues, add a note to the explanation
    if data_issues:
        explanation += " Note: Some data sources were unavailable."
    
    return {"risk": risk, "explanation": explanation, "weather": latest_weather}

@app.get("/", response_class=HTMLResponse)
def home():
    """Fire Risk Dashboard with Synoptic Data Attribution and Dynamic Timestamp"""
    return """<!DOCTYPE html>
<html lang='en'>
<head>
    <meta charset='UTF-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>Sierra City Fire Risk Dashboard</title>
    <link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css' rel='stylesheet'>
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
    </style>
    <script>
        async function fetchFireRisk() {
            const response = await fetch('/fire-risk');
            const data = await response.json();

            const riskDiv = document.getElementById('fire-risk');
            const weatherDetails = document.getElementById('weather-details');
            const timestampDiv = document.getElementById('timestamp');

            // Update fire risk text
            riskDiv.innerText = `Fire Risk: ${data.risk} - ${data.explanation}`;

            // Set appropriate background color based on risk level
            const riskLevel = data.risk;
            let bgClass = 'bg-secondary';  // Default for unknown/error risk

            if (riskLevel === 'Red') {
                bgClass = 'bg-danger text-white'; // Red: Danger
            } else if (riskLevel === 'Yellow') {
                bgClass = 'bg-warning text-dark'; // Yellow: Warning
            }
            // There is no longer a Green status as per requirements

            riskDiv.className = `alert ${bgClass} p-3`;

            // Update weather details
            // Convert temperature from Celsius to Fahrenheit using the formula F = (C * 9/5) + 32
            const tempCelsius = data.weather.air_temp;
            const tempFahrenheit = tempCelsius ? ((tempCelsius * 9/5) + 32).toFixed(1) : 'N/A';
            const soilMoisture = data.weather.soil_moisture_15cm ? data.weather.soil_moisture_15cm : 'N/A';
            const weatherStation = data.weather.data_sources.weather_station;
            const soilStation = data.weather.data_sources.soil_moisture_station;
            
            // Check for data issues
            const dataStatus = data.weather.data_status;
            const hasIssues = dataStatus && dataStatus.issues && dataStatus.issues.length > 0;
            
            // Build the weather details HTML
            let detailsHTML = `<h5>Current Weather Conditions:</h5>`;
            
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
            
            // Handle potentially missing data with fallbacks
            const humidity = data.weather.relative_humidity ? `${data.weather.relative_humidity}%` : 'N/A';
            const windSpeed = data.weather.wind_speed ? `${data.weather.wind_speed} mph` : 'N/A';
            const windGust = data.weather.wind_gust ? `${data.weather.wind_gust} mph` : 'N/A';
            const windGustStation = data.weather.data_sources.wind_gust_station;
            
            detailsHTML += `
                <ul>
                    <li>Temperature: ${tempFahrenheit}°F (converted from ${tempCelsius}°C) <small class="text-muted">[Station: ${weatherStation}]</small></li>
                    <li>Humidity: ${humidity} <small class="text-muted">[Station: ${weatherStation}]</small></li>
                    <li>Wind Speed: ${windSpeed} <small class="text-muted">[Station: ${weatherStation}]</small></li>
                    <li>Wind Gusts: ${windGust} <small class="text-muted">[Station: ${windGustStation}]</small></li>
                    <li>Soil Moisture (15cm depth): ${soilMoisture}% <small class="text-muted">[Station: ${soilStation}]</small></li>
                </ul>
                <div class="alert alert-info p-2 small">
                    <strong>Data Sources:</strong> Temperature, humidity, and wind data from station ${weatherStation}.
                    Soil moisture data from station ${soilStation}.
                    Wind gust data from Weather Underground station ${windGustStation}.
                </div>`;
                
            weatherDetails.innerHTML = detailsHTML;
                
            // Update timestamp
            const now = new Date();
            timestampDiv.innerText = `Last updated: ${now.toLocaleDateString()} at ${now.toLocaleTimeString()}`;
        }

        // Auto-refresh every 5 minutes
        function setupRefresh() {
            fetchFireRisk();
            setInterval(fetchFireRisk, 300000); // 5 minutes
        }

        window.onload = setupRefresh;
    </script>
</head>
<body class='container mt-5'>
    <h1>Sierra City Fire Weather Advisory</h1>
    
    <div id='fire-risk' class='alert alert-info'>Loading fire risk data...</div>
    <div id='weather-details' class='mt-3'></div>
    
    <div class="attribution-container">
        <div id="timestamp" class="timestamp">Last updated: Loading...</div>
        <div class="attribution">
            Weather observations aggregated by&nbsp;<a href="https://www.wunderground.com/" target="_blank">Weather Underground</a>&nbsp;and&nbsp;<a href="https://synopticdata.com/" target="_blank">Synoptic Data</a>
            <img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA0MDAgNDAwIiB3aWR0aD0iMTUwIiBoZWlnaHQ9IjE1MCI+CiAgPGNpcmNsZSBjeD0iMjAwIiBjeT0iMjAwIiByPSIxNDAiIGZpbGw9IiMxYTQ1OTgiIC8+CiAgPHBhdGggZD0iTTYwLDE1MCBDMTUwLDEwMCAyNTAsMTEwIDM1MCwxNTAiIHN0cm9rZT0iIzdkZDBmNSIgc3Ryb2tlLXdpZHRoPSIyNSIgZmlsbD0ibm9uZSIgLz4KICA8cGF0aCBkPSJNNjAsMjAwIEMxNTAsMTUwIDI1MCwxNjAgMzUwLDIwMCIgc3Ryb2tlPSIjN2RkMGY1IiBzdHJva2Utd2lkdGg9IjI1IiBmaWxsPSJub25lIiAvPgogIDxwYXRoIGQ9Ik02MCwyNTAgQzE1MCwyMDAgMjUwLDIxMCAzNTAsMjUwIiBzdHJva2U9IiM3ZGQwZjUiIHN0cm9rZS13aWR0aD0iMjUiIGZpbGw9Im5vbmUiIC8+Cjwvc3ZnPg==" alt="Synoptic Data" class="synoptic-logo">
        </div>
    </div>
</body>
</html>"""
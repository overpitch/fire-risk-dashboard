from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
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
STATION_ID = os.getenv("STATION_ID", "C3DLA")

if not SYNOPTIC_API_KEY:
    logger.warning("No API key provided. Set SYNOPTICDATA_API_KEY environment variable.")

app = FastAPI()

@app.get("/check-env")
def check_env():
    """Check if Render environment variables are available."""
    api_key = os.getenv("SYNOPTICDATA_API_KEY")
    return {
        "SYNOPTICDATA_API_KEY": api_key if api_key else "MISSING"
    }

# Fire risk thresholds
THRESHOLDS = {
    "red": {"temp": 90, "humidity": 15, "wind": 20},
    "yellow": {"temp": 80, "humidity": 25, "wind": 15},
}

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

def get_weather_data(location_id):
    """Get weather data using the temporary token."""
    token = get_api_token()
    if not token:
        return None

    try:
        response = requests.get(
            f"{SYNOPTIC_BASE_URL}/stations/latest?stid={location_id}&token={token}"
        )
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        logger.error(f"Exception during API request: {str(e)}")
        return None

def calculate_fire_risk(weather):
    """Determines fire risk level based on weather data."""
    try:
        temp = float(weather.get("air_temp", 0))
        humidity = float(weather.get("relative_humidity", 100))
        wind = float(weather.get("wind_speed", 0))

        if temp > THRESHOLDS["red"]["temp"] and humidity < THRESHOLDS["red"]["humidity"] and wind > THRESHOLDS["red"]["wind"]:
            return "Red", "High fire risk due to high temperature, low humidity, and strong winds."
        elif temp > THRESHOLDS["yellow"]["temp"] and humidity < THRESHOLDS["yellow"]["humidity"] and wind > THRESHOLDS["yellow"]["wind"]:
            return "Yellow", "Moderate fire risk due to warm conditions."
        return "Green", "Low fire risk at this time."

    except Exception as e:
        logger.error(f"Error calculating fire risk: {str(e)}")
        return "Error", f"Could not calculate risk: {str(e)}"

@app.get("/fire-risk")
def fire_risk():
    """API endpoint to fetch fire risk status."""
    weather_data = get_weather_data(STATION_ID)
    if not weather_data or "STATION" not in weather_data:
        raise HTTPException(status_code=502, detail="Invalid weather data returned from API")

    observations = weather_data["STATION"][0].get("OBSERVATIONS", {})
    latest_weather = {
        "air_temp": observations.get("air_temp_value_1", {}).get("value"),
        "relative_humidity": observations.get("relative_humidity_value_1", {}).get("value"),
        "wind_speed": observations.get("wind_speed_value_1", {}).get("value"),
    }

    risk, explanation = calculate_fire_risk(latest_weather)
    return {"risk": risk, "explanation": explanation, "weather": latest_weather}

@app.get("/", response_class=HTMLResponse)
def home():
    """Restored Fire Risk Dashboard with Correct Colors"""
    return """<!DOCTYPE html>
<html lang='en'>
<head>
    <meta charset='UTF-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>Sierra City Fire Risk Dashboard</title>
    <link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css' rel='stylesheet'>
    <script>
        async function fetchFireRisk() {
            const response = await fetch('/fire-risk');
            const data = await response.json();

            const riskDiv = document.getElementById('fire-risk');
            const weatherDetails = document.getElementById('weather-details');

            // Update fire risk text
            riskDiv.innerText = `Fire Risk: ${data.risk} - ${data.explanation}`;

            // Set appropriate background color based on risk level
            const riskLevel = data.risk;
            let bgClass = 'bg-secondary';  // Default for unknown risk

            if (riskLevel === 'Red') {
                bgClass = 'bg-danger text-white'; // Red: Danger
            } else if (riskLevel === 'Yellow') {
                bgClass = 'bg-warning text-dark'; // Yellow: Warning
            } else if (riskLevel === 'Green') {
                bgClass = 'bg-success bg-opacity-75 text-dark'; // ✅ Light green
            }

            riskDiv.className = `alert ${bgClass} p-3`;

            // Update weather details
            weatherDetails.innerHTML = `
                <h5>Current Weather Conditions:</h5>
                <ul>
                    <li>Temperature: ${data.weather.air_temp}°F</li>
                    <li>Humidity: ${data.weather.relative_humidity}%</li>
                    <li>Wind Speed: ${data.weather.wind_speed} mph</li>
                </ul>`;
        }

        window.onload = fetchFireRisk;
    </script>
</head>
<body class='container mt-5'>
    <h1>Sierra City Fire Risk Dashboard</h1>
    <div id='fire-risk' class='alert alert-info'>Loading fire risk data...</div>
    <div id='weather-details' class='mt-3'></div>
</body>
</html>"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import requests
import os
import logging
from dotenv import load_dotenv  # Load env vars from .env file (for local development)

# Load environment variables from .env if present
load_dotenv()

app = FastAPI()

# Set up logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# API Configuration
API_KEY = os.getenv("SYNOPTICDATA_API_KEY")
if not API_KEY:
    logger.warning("No API key provided. Set SYNOPTICDATA_API_KEY environment variable.")
    
    # API Configuration
    API_KEY = os.getenv("SYNOPTICDATA_API_KEY")
    if not API_KEY:
        logger.warning("No API key provided. Set SYNOPTICDATA_API_KEY environment variable.")

AUTH_URL = "https://api.synopticdata.com/v2/auth"
BASE_URL = "https://api.synopticdata.com/v2/stations/latest"
STATION_ID = os.getenv("STATION_ID", "C3DLA")  # Can be overridden with env var

# Fire risk thresholds
THRESHOLDS = {
    "red": {"temp": 90, "humidity": 15, "wind": 20},
    "yellow": {"temp": 80, "humidity": 25, "wind": 15},  # Added missing wind threshold
}

# Enable/disable debug mode
DEBUG = os.getenv("DEBUG", "false").lower() == "true"


def get_api_token():
    """Get a temporary API token using the permanent API key."""
    try:
        permanent_key = os.environ.get("API_KEY")
        logger.info(f"Attempting to get token with key starting with: {permanent_key[:5] if permanent_key else 'None/Empty'}")
        
        # Your original token request code here
        # For example:
        response = requests.post(
            "https://your-auth-endpoint.com/token",
            headers={"Authorization": f"ApiKey {permanent_key}"},
            # Include any other parameters your API requires
        )
        
        logger.info(f"Token response status code: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"Failed to get token. Response: {response.text}")
            return None
            
        # Your original code to extract the token
        token_data = response.json()
        token = token_data.get("access_token")  # Adjust based on your API's response structure
        
        if token:
            logger.info(f"Successfully acquired token starting with: {token[:5]}***")
        else:
            logger.error("Token was empty or not found in response")
            
        return token
        
    except Exception as e:
        logger.error(f"Exception during token acquisition: {str(e)}")
        return None

def get_weather_data(location_id):
    """Get weather data using the temporary token."""
    try:
        # Get the token first
        token = get_api_token()
        
        if not token:
            logger.error("No token available, cannot make API request")
            return None
            
        logger.info(f"Making API request for location: {location_id}")
        
        # Your original API request code
        # For example:
        response = requests.get(
            f"https://your-api-endpoint.com/weather/{location_id}",
            headers={"Authorization": f"Bearer {token}"},
            # Include any other parameters your API requires
        )
        
        logger.info(f"API response status code: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"API request failed. Response: {response.text}")
            return None
            
        # Your original code to process and return the data
        data = response.json()
        logger.info("Successfully retrieved weather data")
        return data
        
    except Exception as e:
        logger.error(f"Exception during API request: {str(e)}")
        return None

def calculate_fire_risk(weather):
    """Determines fire risk level based on thresholds."""
    try:
        # Check if all required data is present
        required_keys = ["air_temp", "relative_humidity", "wind_speed"]
        for key in required_keys:
            if key not in weather or weather[key] is None:
                logger.warning(f"Missing {key} in weather data")
                return "Unknown", f"Insufficient data: missing {key}"
        
        temp = float(weather["air_temp"])
        humidity = float(weather["relative_humidity"])
        wind = float(weather["wind_speed"])
        
        # Log the values we're using for calculation
        if DEBUG:
            logger.info(f"Calculating risk with temp={temp}°F, humidity={humidity}%, wind={wind}mph")
        
        # Check for red alert conditions
        if (temp > THRESHOLDS["red"]["temp"] and
            humidity < THRESHOLDS["red"]["humidity"] and
            wind > THRESHOLDS["red"]["wind"]):
            return "Red", "High fire risk due to high temperature, low humidity, and strong winds."
        
        # Check for yellow alert conditions - now including wind check
        elif (temp > THRESHOLDS["yellow"]["temp"] and
              humidity < THRESHOLDS["yellow"]["humidity"] and
              wind > THRESHOLDS["yellow"]["wind"]):
            return "Yellow", "Moderate fire risk due to warm conditions."
        
        # Default to green/low risk
        else:
            return "Green", "Low fire risk at this time."
            
    except (ValueError, TypeError) as e:
        # Handle data type conversion errors
        logger.error(f"Error calculating fire risk: {str(e)}")
        return "Error", f"Could not calculate risk: {str(e)}"
    except Exception as e:
        # Catch any other unexpected errors
        logger.error(f"Unexpected error in risk calculation: {str(e)}")
        return "Error", "An unexpected error occurred"

@app.get("/fire-risk")
def fire_risk():
    """API endpoint to fetch fire risk status."""
    try:
        weather_data = get_weather_data()
        
        # Validate API response structure
        if "STATION" not in weather_data or not weather_data["STATION"]:
            logger.error("Invalid API response: missing STATION data")
            raise HTTPException(status_code=502, detail="Invalid weather data returned from API")
            
        station_data = weather_data["STATION"][0]
        if "OBSERVATIONS" not in station_data:
            logger.error("Invalid API response: missing OBSERVATIONS data")
            raise HTTPException(status_code=502, detail="Invalid station data returned from API")
            
        observations = station_data["OBSERVATIONS"]
        
        # Extract latest weather values with error handling
        try:
            latest_weather = {
                "air_temp": observations.get("air_temp_value_1", {}).get("value"),
                "relative_humidity": observations.get("relative_humidity_value_1", {}).get("value"),
                "wind_speed": observations.get("wind_speed_value_1", {}).get("value"),
            }
            
            if DEBUG:
                logger.info(f"Extracted weather data: {latest_weather}")
                
            # Check if we have valid data
            if None in latest_weather.values():
                missing_fields = [k for k, v in latest_weather.items() if v is None]
                logger.warning(f"Missing weather data fields: {missing_fields}")
        except (KeyError, TypeError) as e:
            logger.error(f"Error extracting weather data: {str(e)}")
            raise HTTPException(status_code=502, detail=f"Could not extract weather data: {str(e)}")
        
        # Calculate risk level
        risk, explanation = calculate_fire_risk(latest_weather)
        return {"risk": risk, "explanation": explanation, "weather": latest_weather}
    except HTTPException:
        # Re-raise HTTP exceptions as they are already properly formatted
        raise
    except Exception as e:
        # Catch any other unexpected errors
        logger.error(f"Unexpected error in fire_risk endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while processing the request")

@app.get("/", response_class=HTMLResponse)
def home():
    """Bootstrap-based Fire Risk Dashboard."""
    return """
    <!DOCTYPE html>
    <html lang='en'>
    <head>
        <meta charset='UTF-8'>
        <meta name='viewport' content='width=device-width, initial-scale=1.0'>
        <title>Fire Risk Dashboard</title>
        <link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css' rel='stylesheet'>
        <style>
            .loading-spinner {
                border: 4px solid rgba(0, 0, 0, 0.1);
                width: 36px;
                height: 36px;
                border-radius: 50%;
                border-left-color: #09f;
                animation: spin 1s linear infinite;
                display: inline-block;
                margin-right: 10px;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            .weather-details {
                margin-top: 20px;
                padding: 15px;
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 5px;
            }
        </style>
    </head>
    <body class='container mt-5'>
        <div class="row">
            <div class="col-md-8 offset-md-2">
                <h1 class='mb-3'>Sierra City Fire Risk Dashboard</h1>
                <div id='status-message' class='alert alert-info'>Loading data...</div>
                <div id='fire-risk' class='p-4 text-white mb-3 rounded' style='display: none;'></div>
                <div id='weather-details' class='weather-details text-white' style='display: none;'></div>
                <div class="d-flex justify-content-between align-items-center mt-4">
                    <small class="text-muted">Last updated: <span id="last-updated">Never</span></small>
                    <button id="refresh-btn" class="btn btn-outline-secondary btn-sm">Refresh Now</button>
                </div>
            </div>
        </div>
        <script>
            // Configuration
            const REFRESH_INTERVAL = 300000; // 5 minutes in milliseconds
            let refreshTimer;
            
            // Elements
            const statusMessage = document.getElementById('status-message');
            const riskDiv = document.getElementById('fire-risk');
            const weatherDetails = document.getElementById('weather-details');
            const lastUpdatedSpan = document.getElementById('last-updated');
            const refreshBtn = document.getElementById('refresh-btn');
            
            // Format a date as a readable string
            function formatDateTime(date) {
                return date.toLocaleTimeString() + ' ' + date.toLocaleDateString();
            }
            
            // Show error message
            function showError(message) {
                statusMessage.className = 'alert alert-danger';
                statusMessage.textContent = `Error: ${message}`;
                statusMessage.style.display = 'block';
                riskDiv.style.display = 'none';
                weatherDetails.style.display = 'none';
            }
            
            // Show loading state
            function showLoading() {
                statusMessage.className = 'alert alert-info';
                statusMessage.innerHTML = '<div class="loading-spinner"></div> Fetching latest fire risk data...';
                statusMessage.style.display = 'block';
            }
            
            // Update the UI with fire risk data
            function updateUI(data) {
                // Update risk display
                riskDiv.textContent = `Fire Risk: ${data.risk} - ${data.explanation}`;
                
                // Set appropriate background color based on risk level
                const bgClass = data.risk === 'Red' ? 'bg-danger' :
                                data.risk === 'Yellow' ? 'bg-warning text-dark' :
                                data.risk === 'Green' ? 'bg-success' :
                                data.risk === 'Unknown' ? 'bg-secondary' : 'bg-danger';
                                
                riskDiv.className = `p-4 text-white mb-3 rounded ${bgClass}`;
                if (data.risk === 'Yellow') riskDiv.classList.replace('text-white', 'text-dark');
                
                // Update weather details
                const weather = data.weather;
                weatherDetails.innerHTML = `
                    <h5>Current Weather Conditions:</h5>
                    <ul>
                        <li>Temperature: ${weather.air_temp}°F</li>
                        <li>Humidity: ${weather.relative_humidity}%</li>
                        <li>Wind Speed: ${weather.wind_speed} mph</li>
                    </ul>
                `;
                
                // Update UI visibility
                statusMessage.style.display = 'none';
                riskDiv.style.display = 'block';
                weatherDetails.style.display = 'block';
                weatherDetails.className = `weather-details ${bgClass}`;
                if (data.risk === 'Yellow') weatherDetails.classList.replace('text-white', 'text-dark');
                
                // Update last refreshed time
                lastUpdatedSpan.textContent = formatDateTime(new Date());
            }
            
            // Fetch fire risk data from API
            async function fetchFireRisk() {
                clearTimeout(refreshTimer); // Clear any existing timer
                showLoading();
                
                try {
                    const response = await fetch('/fire-risk');
                    
                    if (!response.ok) {
                        // Handle HTTP errors
                        let errorText = `Server returned ${response.status}`;
                        try {
                            const errorData = await response.json();
                            if (errorData.detail) errorText += `: ${errorData.detail}`;
                        } catch (e) {
                            // If we can't parse the error response, just use status
                        }
                        throw new Error(errorText);
                    }
                    
                    const data = await response.json();
                    updateUI(data);
                } catch (error) {
                    showError(error.message || 'Failed to fetch fire risk data');
                    console.error('Fetch error:', error);
                } finally {
                    // Schedule next refresh
                    refreshTimer = setTimeout(fetchFireRisk, REFRESH_INTERVAL);
                }
            }
            
            // Initial fetch
            fetchFireRisk();
            
            // Manual refresh button
            refreshBtn.addEventListener('click', fetchFireRisk);
        </script>
    </body>
    </html>
    """
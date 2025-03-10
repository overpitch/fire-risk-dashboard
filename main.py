from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import requests
import os
import logging

# Only load .env for local development (not on Render)
if os.getenv("RENDER") is None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("Loaded .env file for local development.")
    except ImportError:
        print("python-dotenv is not installed. Skipping .env loading.")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# API Configuration
SYNOPTIC_API_KEY = os.getenv("SYNOPTICDATA_API_KEY")
SYNOPTIC_BASE_URL = "https://api.synopticdata.com/v2"
STATION_ID = os.getenv("STATION_ID", "C3DLA")  # Default station ID

if not SYNOPTIC_API_KEY:
    logger.warning("No API key provided. Set SYNOPTICDATA_API_KEY environment variable.")

app = FastAPI()

# Fire risk thresholds
THRESHOLDS = {
    "red": {"temp": 90, "humidity": 15, "wind": 20},
    "yellow": {"temp": 80, "humidity": 25, "wind": 15},
}

DEBUG = os.getenv("DEBUG", "false").lower() == "true"


def get_api_token():
    """Get a temporary API token using the permanent API key."""
    if not SYNOPTIC_API_KEY:
        logger.error("SYNOPTIC_API_KEY is not set!")
        return None

    try:
        logger.info("Attempting to get API token...")
        token_url = f"{SYNOPTIC_BASE_URL}/auth?apikey={SYNOPTIC_API_KEY}"
        logger.info(f"Fetching API token from: {token_url}")

        response = requests.get(token_url)
        response.raise_for_status()

        token_data = response.json()
        logger.info(f"Full token response: {token_data}")

        token = token_data.get("TOKEN")  # Fix: Correct key for token

        if token:
            logger.info(f"Successfully acquired token starting with: {token[:5]}***")
        else:
            logger.error("Token was empty or missing in response.")

        return token

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching API token: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected exception during token acquisition: {str(e)}")
        return None


def get_weather_data(location_id):
    """Get weather data using the temporary token."""
    try:
        token = get_api_token()
        if not token:
            logger.error("No token available, cannot make API request")
            return None

        logger.info(f"Making API request for location: {location_id}")

        response = requests.get(
            f"https://api.synopticdata.com/v2/stations/latest?&stid={location_id}&token={token}"
        )

        logger.info(f"API response status code: {response.status_code}")
        logger.info(f"API raw response text: {response.text}")

        if response.status_code != 200:
            logger.error(f"API request failed. Response: {response.text}")
            return None

        try:
            data = response.json()
            logger.info("Successfully retrieved weather data")
            return data
        except ValueError as e:
            logger.error(f"JSON decoding error: {e}")
            return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Exception during API request: {str(e)}")
        return None


def calculate_fire_risk(weather):
    """Determines fire risk level based on weather data."""
    try:
        required_keys = ["air_temp", "relative_humidity", "wind_speed"]
        for key in required_keys:
            if key not in weather or weather[key] is None:
                logger.warning(f"Missing {key} in weather data")
                return "Unknown", f"Insufficient data: missing {key}"

        temp = float(weather["air_temp"])
        humidity = float(weather["relative_humidity"])
        wind = float(weather["wind_speed"])

        if (
            temp > THRESHOLDS["red"]["temp"]
            and humidity < THRESHOLDS["red"]["humidity"]
            and wind > THRESHOLDS["red"]["wind"]
        ):
            return "Red", "High fire risk due to high temperature, low humidity, and strong winds."

        elif (
            temp > THRESHOLDS["yellow"]["temp"]
            and humidity < THRESHOLDS["yellow"]["humidity"]
            and wind > THRESHOLDS["yellow"]["wind"]
        ):
            return "Yellow", "Moderate fire risk due to warm conditions."

        return "Green", "Low fire risk at this time."

    except (ValueError, TypeError) as e:
        logger.error(f"Error calculating fire risk: {str(e)}")
        return "Error", f"Could not calculate risk: {str(e)}"


@app.get("/fire-risk")
def fire_risk():
    """API endpoint to fetch fire risk status."""
    try:
        weather_data = get_weather_data(STATION_ID)
        if not weather_data or "STATION" not in weather_data:
            logger.error("Invalid API response: missing STATION data")
            raise HTTPException(status_code=502, detail="Invalid weather data returned from API")

        station_data = weather_data["STATION"][0]
        if "OBSERVATIONS" not in station_data:
            logger.error("Invalid API response: missing OBSERVATIONS data")
            raise HTTPException(status_code=502, detail="Invalid station data returned from API")

        observations = station_data["OBSERVATIONS"]
        latest_weather = {
            "air_temp": observations.get("air_temp_value_1", {}).get("value"),
            "relative_humidity": observations.get("relative_humidity_value_1", {}).get("value"),
            "wind_speed": observations.get("wind_speed_value_1", {}).get("value"),
        }

        risk, explanation = calculate_fire_risk(latest_weather)
        return {"risk": risk, "explanation": explanation, "weather": latest_weather}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in fire_risk endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while processing the request")


@app.get("/", response_class=HTMLResponse)
def home():
    """Simple homepage."""
    return """
    <html>
    <head><title>Fire Risk Dashboard</title></head>
    <body>
        <h1>Welcome to the Fire Risk Dashboard</h1>
        <p>Visit <a href="/fire-risk">/fire-risk</a> to check fire risk data.</p>
    </body>
    </html>
    """
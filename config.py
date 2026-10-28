import os
import logging
import pytz
from typing import Dict, Any, Optional

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Debug flags - set to False by default for production
DEBUG_API_RESPONSES = os.getenv("DEBUG_API_RESPONSES", "False").lower() == "true"

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

# API Configuration
SYNOPTIC_API_KEY = os.getenv("SYNOPTICDATA_API_KEY")
SYNOPTIC_BASE_URL = "https://api.synopticdata.com/v2"

# Station IDs (hard-coded)
SOIL_MOISTURE_STATION_ID = "C3DLA"  # Station for soil moisture data
WEATHER_STATION_ID = "SEYC1"        # Station for temperature and humidity
WIND_STATION_ID = "629PG"           # Station for wind speed and gust data (PG&E Sand Shed)

# Fire risk thresholds from environment variables
THRESH_TEMP = float(os.getenv("THRESH_TEMP", 75))            # Temperature threshold in Fahrenheit
THRESH_HUMID = float(os.getenv("THRESH_HUMID", 15))          # Humidity threshold in percent
THRESH_WIND = float(os.getenv("THRESH_WIND", 15))            # Wind speed threshold in mph
THRESH_GUSTS = float(os.getenv("THRESH_GUSTS", 20))          # Wind gust threshold in mph
THRESH_SOIL_MOIST = float(os.getenv("THRESH_SOIL_MOIST", 10)) # Soil moisture threshold in percent

# Convert temperature threshold from Fahrenheit to Celsius for internal use
THRESH_TEMP_CELSIUS = (THRESH_TEMP - 32) * 5/9

# Number of proxies in front of the app that append to X-Forwarded-For (Render's proxy = 1).
# 0 = ignore the header and use the connecting address (default outside Render).
TRUSTED_PROXY_HOPS = int(os.getenv("TRUSTED_PROXY_HOPS", "1" if IS_PRODUCTION else "0"))

# Folder for the weather cache file, which also remembers the last risk level and alert time.
# On Render, point this at the persistent disk; the app folder is replaced on every deploy.
CACHE_DIR = os.getenv("CACHE_DIR", "data")

# Admin test alerts (from "Test System Recognition of Red Status") go only to this address.
# If unset, test runs never send email.
TEST_ALERT_EMAIL = os.getenv("TEST_ALERT_EMAIL")

# Timezone configuration
TIMEZONE = pytz.timezone('America/Los_Angeles')

# Log configuration values
if not SYNOPTIC_API_KEY:
    logger.warning("No API key provided. Set SYNOPTICDATA_API_KEY environment variable.")

logger.info(f"Using thresholds: TEMP={THRESH_TEMP}°F, "
            f"HUMID={THRESH_HUMID}%, WIND={THRESH_WIND}mph, "
            f"GUSTS={THRESH_GUSTS}mph, SOIL={THRESH_SOIL_MOIST}%")

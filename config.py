import os
import logging
import pytz
from typing import Dict, Any, Optional

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

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

# Weather Underground API - No longer used
# WUNDERGROUND_API_KEY = os.getenv("WUNDERGROUND_API_KEY")
# WUNDERGROUND_BASE_URL = "https://api.weather.com/v2/pws"

# Station IDs (hard-coded)
SOIL_MOISTURE_STATION_ID = "C3DLA"  # Station for soil moisture data
WEATHER_STATION_ID = "SEYC1"        # Station for temperature and humidity
WIND_STATION_ID = "629PG"           # Station for wind speed and gust data (PG&E Sand Shed)
WIND_GUST_STATION_ID = "629PG"      # Same as WIND_STATION_ID, defined for backwards compatibility
# No longer using Weather Underground stations for wind gust data
# WUNDERGROUND_STATION_IDS = ["KCASIERR68", "KCASIERR63", "KCASIERR72"]

# Fire risk thresholds from environment variables
THRESH_TEMP = float(os.getenv("THRESH_TEMP", 75))            # Temperature threshold in Fahrenheit
THRESH_HUMID = float(os.getenv("THRESH_HUMID", 15))          # Humidity threshold in percent
THRESH_WIND = float(os.getenv("THRESH_WIND", 15))            # Wind speed threshold in mph
THRESH_GUSTS = float(os.getenv("THRESH_GUSTS", 20))          # Wind gust threshold in mph
THRESH_SOIL_MOIST = float(os.getenv("THRESH_SOIL_MOIST", 10)) # Soil moisture threshold in percent

# Convert temperature threshold from Fahrenheit to Celsius for internal use
THRESH_TEMP_CELSIUS = (THRESH_TEMP - 32) * 5/9

# Timezone configuration
TIMEZONE = pytz.timezone('America/Los_Angeles')

# Log configuration values
if not SYNOPTIC_API_KEY:
    logger.warning("No API key provided. Set SYNOPTICDATA_API_KEY environment variable.")

# No longer warning about Weather Underground API key as we don't use it anymore
# if not WUNDERGROUND_API_KEY:
#     logger.warning("No Weather Underground API key provided. Set WUNDERGROUND_API_KEY environment variable.")

logger.info(f"Using thresholds: TEMP={THRESH_TEMP}°F, "
            f"HUMID={THRESH_HUMID}%, WIND={THRESH_WIND}mph, "
            f"GUSTS={THRESH_GUSTS}mph, SOIL={THRESH_SOIL_MOIST}%")

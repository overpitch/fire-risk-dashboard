import requests
import json
import logging
from typing import Dict, Any, Optional

from config import (
    SYNOPTIC_API_KEY, SYNOPTIC_BASE_URL,
    SOIL_MOISTURE_STATION_ID, WEATHER_STATION_ID, WIND_STATION_ID,
    logger
)

def get_api_token() -> Optional[str]:
    """Get a temporary API token using the permanent API key."""
    if not SYNOPTIC_API_KEY:
        logger.error("🚨 API KEY NOT FOUND! Environment variable is missing.")
        return None

    try:
        token_url = f"{SYNOPTIC_BASE_URL}/auth?apikey={SYNOPTIC_API_KEY}"
        logger.info(f"🔑 Attempting to fetch API token from Synoptic API")

        response = requests.get(token_url)
        response.raise_for_status()
        token_data = response.json()

        token = token_data.get("TOKEN")
        if token:
            logger.info(f"✅ Successfully received API token from Synoptic API")
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

def get_weather_data(location_ids: str, retry_count: int = 0, max_retries: int = 2) -> Optional[Dict[str, Any]]:
    """Get weather data using the temporary token.
    
    Args:
        location_ids: A string of comma-separated station IDs
        retry_count: Current retry attempt (used internally for recursion)
        max_retries: Maximum number of retries for 401 errors
    
    Returns:
        Dictionary containing the weather data or None if an error occurred
    """
    token = get_api_token()
    if not token:
        return None

    try:
        # Construct the URL
        request_url = f"{SYNOPTIC_BASE_URL}/stations/latest?stid={location_ids}&token={token}"
        logger.info(f"🔍 Requesting weather data for stations: {location_ids}")

        response = requests.get(request_url)
        
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

# Weather Underground data retrieval function has been removed as we now use Synoptic for wind gust data

def get_synoptic_data() -> Optional[Dict[str, Any]]:
    """Get weather data from Synoptic API for weather, soil moisture, and wind stations.
    
    Returns:
        Dictionary containing the weather data or None if an error occurred
    """
    station_ids = f"{SOIL_MOISTURE_STATION_ID},{WEATHER_STATION_ID},{WIND_STATION_ID}"
    return get_weather_data(station_ids)

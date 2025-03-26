import requests
import json
import logging
from typing import Dict, Any, Optional

from config import (
    SYNOPTIC_API_KEY, SYNOPTIC_BASE_URL,
    WUNDERGROUND_API_KEY, WUNDERGROUND_BASE_URL,
    SOIL_MOISTURE_STATION_ID, WEATHER_STATION_ID, WUNDERGROUND_STATION_IDS,
    logger
)

def get_api_token() -> Optional[str]:
    """Get a temporary API token using the permanent API key."""
    if not SYNOPTIC_API_KEY:
        logger.error("🚨 API KEY NOT FOUND! Environment variable is missing.")
        return None

    try:
        token_url = f"{SYNOPTIC_BASE_URL}/auth?apikey={SYNOPTIC_API_KEY}"
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

def get_wunderground_data(station_ids: list = None) -> Dict[str, Optional[Dict[str, Any]]]:
    """Get weather data from Weather Underground API for multiple stations.
    
    Args:
        station_ids: List of Weather Underground station IDs (e.g. ["KCASIERR68", "KCASIERR63"])
                    If None, uses the default stations from config
    
    Returns:
        Dictionary mapping station IDs to their respective API responses or None if an error occurred
        Example: {"KCASIERR68": {response_data}, "KCASIERR63": None}
    """
    if station_ids is None:
        station_ids = WUNDERGROUND_STATION_IDS
        
    if not WUNDERGROUND_API_KEY:
        logger.error("🚨 WEATHER UNDERGROUND API KEY NOT FOUND! Environment variable is missing.")
        return {station_id: None for station_id in station_ids}
    
    # Initialize results dictionary
    results = {}
    
    # Fetch data for each station
    for station_id in station_ids:
        try:
            # Build the URL to get the current conditions for the station
            url = f"{WUNDERGROUND_BASE_URL}/observations/current?stationId={station_id}&format=json&units=e&apiKey={WUNDERGROUND_API_KEY}"
            logger.info(f"🔎 Fetching Weather Underground data for station {station_id}")
            
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            
            # Check if we have the expected data structure
            if "observations" in data and len(data["observations"]) > 0:
                logger.info(f"✅ Successfully received data from Weather Underground for station {station_id}")
                results[station_id] = data
            else:
                logger.error(f"🚨 No observations found in Weather Underground response for station {station_id}")
                results[station_id] = None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"🚨 Error fetching Wind Gust data from Weather Underground for station {station_id}: {e}")
            results[station_id] = None
    
    return results

def get_synoptic_data() -> Optional[Dict[str, Any]]:
    """Get weather data from Synoptic API for both weather and soil moisture stations.
    
    Returns:
        Dictionary containing the weather data or None if an error occurred
    """
    station_ids = f"{SOIL_MOISTURE_STATION_ID},{WEATHER_STATION_ID}"
    return get_weather_data(station_ids)

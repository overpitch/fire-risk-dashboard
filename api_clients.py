import requests
import json
import logging
import os
import re
import time
from typing import Dict, Any, Optional, Tuple

from config import (
    SYNOPTIC_API_KEY, SYNOPTIC_BASE_URL,
    SOIL_MOISTURE_STATION_ID, WEATHER_STATION_ID, WIND_STATION_ID,
    DEBUG_API_RESPONSES, logger, IS_PRODUCTION
)

# Path for fallback data cache
FALLBACK_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "synoptic_fallback_data.json")

def configure_production_environment() -> Dict[str, Any]:
    """
    Configure request parameters for API calls.
    
    This function was previously attempting to mimic production environment
    with custom headers and proxies, but this was causing 403 Forbidden errors.
    
    Returns:
        Dict of parameters for requests to use (empty headers, no proxies)
    """
    # Use default request parameters regardless of environment
    # This fixes the 403 Forbidden errors from the Synoptic API
    logger.info("🔍 Using default request parameters for best API compatibility")
    return {
        "headers": {},  # Empty headers - use default browser-like ones
        "proxies": None  # No proxies
    }

def get_api_token(request_params: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Get a temporary API token using the permanent API key.
    
    Args:
        request_params: Optional dictionary of request parameters (headers, proxies, etc)
    
    Returns:
        A validated API token or None if unable to obtain a valid token
    """
    if not SYNOPTIC_API_KEY:
        logger.error("🚨 API KEY NOT FOUND! Environment variable is missing.")
        return None

    if request_params is None:
        request_params = configure_production_environment()

    try:
        token_url = f"{SYNOPTIC_BASE_URL}/auth?apikey={SYNOPTIC_API_KEY}"
        logger.info(f"🔑 Attempting to fetch API token from Synoptic API")

        response = requests.get(
            token_url, 
            headers=request_params.get("headers", {}),
            proxies=request_params.get("proxies")
        )
        response.raise_for_status()
        token_data = response.json()

        token = token_data.get("TOKEN")
        if token:
            # Validate the token format - should be an alphanumeric string 
            # typically 32-64 characters long
            if validate_token_format(token):
                logger.info(f"✅ Successfully received API token from Synoptic API")
                return token
            else:
                logger.error(f"🚨 Received malformed token from API: {token[:10]}...")
                return None
        else:
            logger.error("🚨 Token was empty or missing in response.")
            # Check if there's an error message in the response
            if "error" in token_data:
                logger.error(f"🚨 API error message: {token_data['error']}")
            return None

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

def validate_token_format(token: str) -> bool:
    """
    Validate that a token appears to be in the correct format.
    
    Args:
        token: The token string to validate
        
    Returns:
        True if the token appears valid, False otherwise
    """
    # Synoptic tokens are typically alphanumeric strings of 32-64 characters
    if not token:
        return False
    
    # Check that the token matches the expected pattern (alphanumeric, reasonable length)
    token_pattern = re.compile(r'^[a-zA-Z0-9]{24,64}$')
    return bool(token_pattern.match(token))

def calculate_backoff_time(retry_count: int, base_delay: float = 1.0) -> float:
    """
    Calculate the exponential backoff time for retries.
    
    Args:
        retry_count: The current retry attempt number (0-based)
        base_delay: The base delay in seconds
        
    Returns:
        Delay time in seconds
    """
    # Exponential backoff with a small random factor for jitter
    import random
    max_delay = 30  # Cap the delay at 30 seconds
    delay = min(base_delay * (2 ** retry_count), max_delay)
    # Add a small random jitter (±10%)
    jitter = delay * 0.1
    return delay + random.uniform(-jitter, jitter)

def get_weather_data(location_ids: str, retry_count: int = 0, max_retries: int = 4) -> Optional[Dict[str, Any]]:
    """Get weather data using the temporary token with production environment simulation.
    
    Args:
        location_ids: A string of comma-separated station IDs
        retry_count: Current retry attempt (used internally for recursion)
        max_retries: Maximum number of retries for 401 errors
    
    Returns:
        Dictionary containing the weather data or None if an error occurred
    """
    request_params = configure_production_environment()
    token = get_api_token(request_params)
    
    if not token:
        logger.error("🚨 Could not obtain API token, using fallback data if available")
        if retry_count < max_retries:
            # Apply exponential backoff before retrying
            backoff_time = calculate_backoff_time(retry_count)
            logger.info(f"🕒 Backing off for {backoff_time:.2f} seconds before retry {retry_count + 1}/{max_retries}")
            time.sleep(backoff_time)
            
            # Try again with a fresh token
            return get_weather_data(location_ids, retry_count + 1, max_retries)
        return load_fallback_data() if not IS_PRODUCTION else None

    try:
        # Construct the URL
        request_url = f"{SYNOPTIC_BASE_URL}/stations/latest?stid={location_ids}&token={token}"
        logger.info(f"🔍 Requesting weather data for stations: {location_ids}")

        # Add more detailed logging about the request
        logger.info(f"📡 Full request URL: {request_url}")
        logger.info(f"🔑 Using token: {token[:10]}...")
        if request_params.get("headers"):
            logger.info(f"🔤 Using headers: {request_params.get('headers')}")
        if request_params.get("proxies"):
            logger.info(f"🔄 Using proxy: {request_params.get('proxies')}")

        # Make the request with production environment parameters
        try:
            response = requests.get(
                request_url, 
                headers=request_params.get("headers", {}),
                proxies=request_params.get("proxies"),
                timeout=10
            )
            
            logger.info(f"📊 Response status: {response.status_code}")
            logger.info(f"📝 Response headers: {dict(response.headers)}")
            
            # If the request fails with a 403 error
            if response.status_code == 403:
                logger.warning("🚨 Permission denied (403 Forbidden) - account access restricted")
                
                # If we're in a development environment, use cached fallback data
                if not IS_PRODUCTION:
                    logger.info("🏠 Development environment detected - using fallback data")
                    return load_fallback_data()
                else:
                    # In production, this should work - log the error and retry once
                    logger.error("🚨 403 Forbidden error in production - unexpected!")
                    try:
                        error_data = response.json()
                        logger.error(f"🚨 API error details: {json.dumps(error_data)}")
                    except:
                        logger.error(f"🚨 API error response text: {response.text[:200]}")
                    
                    # Retry once in production on 403 error
                    if retry_count < 1:
                        logger.info(f"🔄 Retrying once for 403 error in production")
                        return get_weather_data(location_ids, retry_count + 1, max_retries)
                    else:
                        logger.error(f"❌ Repeated 403 error in production - check account settings")
                        return None
            
            # Handle other errors
            elif response.status_code == 401:
                logger.error("🚨 Authentication failed (401 Unauthorized). The API token may be invalid or expired.")
                # Try to get error details from response
                try:
                    error_data = response.json()
                    logger.error(f"🚨 API error details: {json.dumps(error_data)}")
                except:
                    logger.error(f"🚨 API error response text: {response.text[:200]}")
                
                # If we haven't exceeded max retries, get a fresh token and try again
                if retry_count < max_retries:
                    # Apply exponential backoff before retrying
                    backoff_time = calculate_backoff_time(retry_count)
                    logger.info(f"🕒 Backing off for {backoff_time:.2f} seconds before retry {retry_count + 1}/{max_retries}")
                    time.sleep(backoff_time)
                    
                    # Check if the error specifically mentions "Invalid token"
                    invalid_token_error = False
                    try:
                        error_message = response.json().get("SUMMARY", {}).get("RESPONSE_MESSAGE", "")
                        if "Invalid token" in error_message:
                            invalid_token_error = True
                            logger.warning(f"🔑 API reports invalid token format: {error_message}")
                    except:
                        pass
                    
                    logger.info(f"🔄 Retrying with a fresh token (attempt {retry_count + 1}/{max_retries})")
                    return get_weather_data(location_ids, retry_count + 1, max_retries)
                else:
                    logger.error(f"❌ Exceeded maximum retries ({max_retries}) for 401 errors")
                    return load_fallback_data() if not IS_PRODUCTION else None
            
            response.raise_for_status()
            data = response.json()
            
            # Validate that the response contains the expected STATION field
            if "STATION" not in data:
                logger.error("🚨 Weather API response missing STATION data")
                if DEBUG_API_RESPONSES:
                    logger.debug(f"🔍 Response keys available: {list(data.keys())}")
                    
                # Return fallback data in development
                if not IS_PRODUCTION:
                    return load_fallback_data()
                return None
            
            # If successful, cache this data for future fallback
            if not IS_PRODUCTION:
                save_fallback_data(data)
            
            logger.info(f"✅ Successfully received data from Synoptic API")
            
            # Add debug logging of response structure when enabled
            if DEBUG_API_RESPONSES:
                logger.debug(f"🔍 API Response Keys: {list(data.keys())}")
                if 'STATION' in data:
                    logger.debug(f"🔍 Number of stations: {len(data.get('STATION', []))}")
                    station_ids = [s.get('STID') for s in data.get('STATION', [])]
                    logger.debug(f"🔍 Station IDs in response: {station_ids}")
                else:
                    logger.debug(f"🔍 STATION key missing. Full response sample: {json.dumps(data, default=str)[:500]}...")
                    
            return data
            
        except requests.exceptions.Timeout:
            logger.error("🚨 Request timed out - API endpoint not responding in a timely manner")
            return load_fallback_data() if not IS_PRODUCTION else None
        except requests.exceptions.ConnectionError:
            logger.error("🚨 Connection error - Unable to connect to API endpoint")
            return load_fallback_data() if not IS_PRODUCTION else None
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Exception during API request: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                logger.error(f"🚨 API error details: {json.dumps(error_data)}")
            except:
                logger.error(f"🚨 API error status code: {e.response.status_code}")
                logger.error(f"🚨 API error response text: {e.response.text[:200]}")
        return load_fallback_data() if not IS_PRODUCTION else None

def create_data_directory():
    """Create data directory if it doesn't exist"""
    data_dir = os.path.dirname(FALLBACK_DATA_PATH)
    if not os.path.exists(data_dir):
        try:
            os.makedirs(data_dir)
            logger.info(f"📁 Created data directory: {data_dir}")
        except Exception as e:
            logger.error(f"🚨 Failed to create data directory: {e}")

def save_fallback_data(data: Dict[str, Any]) -> bool:
    """
    Save API data for future fallback use.
    
    Args:
        data: The API response data to save
    
    Returns:
        True if successful, False otherwise
    """
    try:
        create_data_directory()
        with open(FALLBACK_DATA_PATH, 'w') as f:
            json.dump(data, f)
        logger.info(f"💾 Saved fallback data to {FALLBACK_DATA_PATH}")
        return True
    except Exception as e:
        logger.error(f"🚨 Failed to save fallback data: {e}")
        return False

def load_fallback_data() -> Optional[Dict[str, Any]]:
    """
    Load fallback data from cache file.
    
    Returns:
        Cached API data or None if no cache exists
    """
    try:
        if os.path.exists(FALLBACK_DATA_PATH):
            with open(FALLBACK_DATA_PATH, 'r') as f:
                data = json.load(f)
            logger.info(f"📂 Loaded fallback data from {FALLBACK_DATA_PATH}")
            
            # Inject a fallback indicator
            if isinstance(data, dict):
                if "SUMMARY" not in data:
                    data["SUMMARY"] = {}
                data["SUMMARY"]["FALLBACK_DATA"] = True
                
            return data
        else:
            logger.warning(f"⚠️ No fallback data available at {FALLBACK_DATA_PATH}")
            return None
    except Exception as e:
        logger.error(f"🚨 Failed to load fallback data: {e}")
        return None

def get_synoptic_data() -> Optional[Dict[str, Any]]:
    """Get weather data from Synoptic API for weather, soil moisture, and wind stations.
    
    Returns:
        Dictionary containing the weather data or None if an error occurred
    """
    station_ids = f"{SOIL_MOISTURE_STATION_ID},{WEATHER_STATION_ID},{WIND_STATION_ID}"
    data = get_weather_data(station_ids)
    
    # Validate that the response contains the expected STATION field
    if data and "STATION" not in data and "SUMMARY" not in data.get("FALLBACK_DATA", {}):
        logger.error("Weather API response missing STATION data")
        if DEBUG_API_RESPONSES:
            # Log keys and response info to help diagnose
            logger.debug(f"🚨 Response keys available: {list(data.keys())}")
            if "SUMMARY" in data:
                logger.debug(f"🚨 API Summary: {data.get('SUMMARY')}")
            if "status" in data:
                logger.debug(f"🚨 API Status: {data.get('status')}")
            logger.debug(f"🚨 Response sample: {json.dumps(data, default=str)[:500]}...")
        
        # Return None to trigger cache fallback
        return None
    
    # Log if we're using fallback data
    if data and data.get("SUMMARY", {}).get("FALLBACK_DATA", False):
        logger.info("📋 Using fallback data from cache")
        
    return data

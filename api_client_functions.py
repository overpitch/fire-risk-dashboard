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

def get_weather_data(location_ids, retry_count=0, max_retries=2):
    """Get weather data using the temporary token.
    
    Args:
        location_ids: A string of comma-separated station IDs
        retry_count: Current retry attempt (used internally for recursion)
        max_retries: Maximum number of retries for 401 errors
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
        
        # If all thresholds are exceeded: RED, otherwise: ORANGE
        if temp_exceeded and humidity_exceeded and wind_exceeded and gusts_exceeded and soil_exceeded:
            return "Red", "High fire risk due to high temperature, low humidity, strong winds, high wind gusts, and low soil moisture."
        else:
            return "Orange", "Low or Moderate Fire Risk. Exercise standard prevention practices."

    except Exception as e:
        logger.error(f"Error calculating fire risk: {str(e)}")
        return "Error", f"Could not calculate risk: {str(e)}"

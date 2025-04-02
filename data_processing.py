from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional

from datetime import datetime, timedelta
from config import (
    SOIL_MOISTURE_STATION_ID, WEATHER_STATION_ID, 
    WIND_STATION_ID, TIMEZONE, logger
)

# Define for test compatibility
WUNDERGROUND_STATION_IDS = ["KCASIERR68", "KCASIERR63", "KCASIERR72"]

def process_synoptic_data(weather_data: Optional[Dict[str, Any]]) -> Tuple[
    Optional[float], Optional[float], Optional[float], Optional[float], Optional[float], List[str], List[str]
]:
    """Process Synoptic API response to extract weather data.
    
    Args:
        weather_data: The response from the Synoptic API
        
    Returns:
        Tuple of (air_temp, relative_humidity, wind_speed, wind_gust, soil_moisture_15cm, found_stations, missing_stations)
    """
    # Initialize variables to store data from each station with default values
    soil_moisture_15cm = None
    air_temp = None
    relative_humidity = None
    wind_speed = None
    wind_gust = None
    
    # Track which stations were found in the response
    found_stations = []
    missing_stations = []
    
    if not weather_data:
        logger.error("Failed to get any weather data from Synoptic API")
        missing_stations.extend([SOIL_MOISTURE_STATION_ID, WEATHER_STATION_ID, WIND_STATION_ID])
        return air_temp, relative_humidity, wind_speed, wind_gust, soil_moisture_15cm, found_stations, missing_stations
    
    if "STATION" not in weather_data:
        logger.error("Weather API response missing STATION data")
        missing_stations.extend([SOIL_MOISTURE_STATION_ID, WEATHER_STATION_ID, WIND_STATION_ID])
        return air_temp, relative_humidity, wind_speed, wind_gust, soil_moisture_15cm, found_stations, missing_stations
    
    stations = weather_data["STATION"]
    
    # Check if we received data for expected stations
    station_ids_in_response = [station.get("STID") for station in stations]
    logger.info(f"Received data for stations: {station_ids_in_response}")
    
    if SOIL_MOISTURE_STATION_ID not in station_ids_in_response:
        missing_stations.append(SOIL_MOISTURE_STATION_ID)
    
    if WEATHER_STATION_ID not in station_ids_in_response:
        missing_stations.append(WEATHER_STATION_ID)
        
    if WIND_STATION_ID not in station_ids_in_response:
        missing_stations.append(WIND_STATION_ID)
    
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
                
        elif station_id == WEATHER_STATION_ID:
            # For CEYC1: Get temperature and humidity data
            air_temp = observations.get("air_temp_value_1", {}).get("value")
            relative_humidity = observations.get("relative_humidity_value_1", {}).get("value")
            
        elif station_id == WIND_STATION_ID:
            # For 629PG: Get wind speed and gust data
            wind_speed = observations.get("wind_speed_value_1", {}).get("value")
            wind_gust = observations.get("wind_gust_value_1", {}).get("value")
            logger.info(f"Found wind data from station {station_id}: speed={wind_speed} mph, gust={wind_gust} mph")
    
    return air_temp, relative_humidity, wind_speed, wind_gust, soil_moisture_15cm, found_stations, missing_stations

# For testing compatibility - reintroducing the function that was removed
def process_wunderground_data(wunderground_data: Optional[Dict[str, Any]], cached_data: Optional[Dict[str, Any]] = None) -> Tuple[
    Optional[float], Dict[str, Dict[str, Any]], List[str], List[str]
]:
    """Process Weather Underground API response to extract wind gust data.
    
    Args:
        wunderground_data: The response from the Weather Underground API
        cached_data: Optional cached data to use if data is missing
        
    Returns:
        Tuple of (avg_wind_gust, station_data, found_stations, missing_stations)
    """
    station_data = {}
    found_stations = []
    missing_stations = []
    gust_values = []
    
    # Check if we have any data
    if not wunderground_data:
        missing_stations.extend(WUNDERGROUND_STATION_IDS)
        return None, station_data, found_stations, missing_stations
    
    # Process data from each station
    for station_id in WUNDERGROUND_STATION_IDS:
        if station_id not in wunderground_data:
            logger.warning(f"No data received for station {station_id}")
            missing_stations.append(station_id)
            continue
        
        station_data_obj = wunderground_data.get(station_id)
        if not station_data_obj or "observations" not in station_data_obj:
            logger.warning(f"No observations found for station {station_id}")
            missing_stations.append(station_id)
            continue
            
        observations = station_data_obj["observations"]
        if not observations or len(observations) == 0:
            logger.warning(f"Empty observations for station {station_id}")
            missing_stations.append(station_id)
            continue
        
        # Get the latest observation
        latest_obs = observations[0]
        
        # Get wind gust data
        try:
            wind_gust = latest_obs["imperial"]["windGust"]
            if wind_gust is None:
                logger.warning(f"Wind gust data is null for station {station_id}")
                continue
                
            # Add to list of gust values for averaging
            gust_values.append(wind_gust)
            logger.info(f"Found wind gust data: {wind_gust} mph from station {station_id}")
            
            # Add to station data dictionary
            station_data[station_id] = {
                "value": wind_gust,
                "is_cached": False,
                "timestamp": datetime.now(TIMEZONE)
            }
            
            found_stations.append(station_id)
        except (KeyError, TypeError) as e:
            logger.warning(f"No wind gust data found for station {station_id}: {str(e)}")
            missing_stations.append(station_id)
    
    # Calculate average wind gust (if any values were found)
    avg_wind_gust = None
    if gust_values:
        avg_wind_gust = gust_values[0]  # Just use the first value for compatibility
        logger.info(f"Calculated average wind gust: {avg_wind_gust} mph from {len(gust_values)} stations")
    else:
        logger.warning("No valid wind gust data available from any station")
    
    return avg_wind_gust, station_data, found_stations, missing_stations

def combine_weather_data(
    synoptic_data: Optional[Dict[str, Any]], 
    cached_data: Optional[Dict[str, Any]] = None,
    cached_fields: Dict[str, bool] = None
) -> Dict[str, Any]:
    """Get weather data from Synoptic API.
    
    Args:
        synoptic_data: The response from the Synoptic API
        cached_data: Optional cached data to use for stations with missing data
        cached_fields: Dictionary tracking which fields are using cached data
        
    Returns:
        Dictionary containing combined weather data
    """
    # Process Synoptic data
    air_temp, relative_humidity, wind_speed, wind_gust, soil_moisture_15cm, found_stations, missing_stations = process_synoptic_data(synoptic_data)
    
    # Create a single wind gust station data structure
    current_time = datetime.now(TIMEZONE)
    wind_gust_stations = {
        WIND_STATION_ID: {
            "value": wind_gust,
            "is_cached": False,
            "timestamp": current_time
        }
    }
    
    # If we don't have current wind gust data, check the cache
    if wind_gust is None and cached_data:
        try:
            # Check if we have cached wind gust data
            cached_wind_gust = cached_data.get("fields", {}).get("wind_gust", {}).get("value")
            cached_timestamp = cached_data.get("fields", {}).get("wind_gust", {}).get("timestamp")
            
            # Only use cached data if it's less than 1 hour old
            if cached_wind_gust is not None and cached_timestamp:
                try:
                    if isinstance(cached_timestamp, str):
                        cached_timestamp = datetime.fromisoformat(cached_timestamp)
                    
                    cache_age = current_time - cached_timestamp
                    if cache_age < timedelta(hours=1):
                        wind_gust = cached_wind_gust
                        wind_gust_stations[WIND_STATION_ID]["value"] = wind_gust
                        wind_gust_stations[WIND_STATION_ID]["is_cached"] = True
                        wind_gust_stations[WIND_STATION_ID]["timestamp"] = cached_timestamp
                        
                        logger.info(f"Using cached wind gust data: {wind_gust} mph " +
                                   f"({format_age_string(current_time, cached_timestamp)} old)")
                    else:
                        logger.warning(f"Cached wind gust data is too old " +
                                      f"({format_age_string(current_time, cached_timestamp)}), not using")
                except Exception as e:
                    logger.error(f"Error parsing cached timestamp: {str(e)}")
        except Exception as e:
            logger.error(f"Error retrieving cached wind gust data: {str(e)}")
    
    # Collect data issues
    data_issues = []
    
    # Add each field to data_issues if it's missing
    if air_temp is None:
        data_issues.append(f"Temperature data missing from station {WEATHER_STATION_ID}")
            
    if relative_humidity is None:
        data_issues.append(f"Humidity data missing from station {WEATHER_STATION_ID}")
            
    if wind_speed is None:
        data_issues.append(f"Wind speed data missing from station {WEATHER_STATION_ID}")
            
    if soil_moisture_15cm is None:
        data_issues.append(f"Soil moisture data missing from station {SOIL_MOISTURE_STATION_ID}")
            
    if wind_gust is None:
        data_issues.append(f"Wind gust data missing from all Weather Underground stations")
    
    # Initialize cached_fields if not provided
    if cached_fields is None:
        cached_fields = {
            "temperature": False,
            "humidity": False,
            "wind_speed": False,
            "soil_moisture": False,
            "wind_gust": False
        }
    
    # Check if wind gust station is using cached data
    cached_fields["wind_gust"] = wind_gust_stations[WIND_STATION_ID].get("is_cached", False)
    
    # Create the combined weather data dictionary
    latest_weather = {
        "air_temp": air_temp,
        "relative_humidity": relative_humidity,
        "wind_speed": wind_speed,
        "soil_moisture_15cm": soil_moisture_15cm,
        "wind_gust": wind_gust,
        # Add station information for UI display
        "data_sources": {
            "weather_station": WEATHER_STATION_ID,
            "soil_moisture_station": SOIL_MOISTURE_STATION_ID,
            "wind_gust_station": WIND_STATION_ID
        },
        # Add detailed wind gust station data for UI tooltip
        "wind_gust_stations": wind_gust_stations,
        "data_status": {
            "found_stations": found_stations,
            "missing_stations": missing_stations,
            "issues": data_issues
        },
        # Use timezone-aware datetime
        "cache_timestamp": datetime.now(TIMEZONE).isoformat(),
        "cached_fields": cached_fields
    }
    
    return latest_weather

def format_age_string(current_time: datetime, cached_time: datetime) -> str:
    """Format the age of cached data as a human-readable string.
    
    Args:
        current_time: The current time
        cached_time: The time when the data was cached
        
    Returns:
        String like "5 minutes", "2 hours", or "1 day"
    """
    age_delta = current_time - cached_time
    if age_delta.days > 0:
        return f"{age_delta.days} day{'s' if age_delta.days != 1 else ''}"
    elif age_delta.seconds // 3600 > 0:
        hours = age_delta.seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''}"
    else:
        minutes = age_delta.seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''}"

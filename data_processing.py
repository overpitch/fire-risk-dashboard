from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional

from config import (
    SOIL_MOISTURE_STATION_ID, WEATHER_STATION_ID, 
    WUNDERGROUND_STATION_ID, TIMEZONE, logger
)

def process_synoptic_data(weather_data: Optional[Dict[str, Any]]) -> Tuple[
    Optional[float], Optional[float], Optional[float], Optional[float], List[str], List[str]
]:
    """Process Synoptic API response to extract weather data.
    
    Args:
        weather_data: The response from the Synoptic API
        
    Returns:
        Tuple of (air_temp, relative_humidity, wind_speed, soil_moisture_15cm, found_stations, missing_stations)
    """
    # Initialize variables to store data from each station with default values
    soil_moisture_15cm = None
    air_temp = None
    relative_humidity = None
    wind_speed = None
    
    # Track which stations were found in the response
    found_stations = []
    missing_stations = []
    
    if not weather_data:
        logger.error("Failed to get any weather data from Synoptic API")
        missing_stations.extend([SOIL_MOISTURE_STATION_ID, WEATHER_STATION_ID])
        return air_temp, relative_humidity, wind_speed, soil_moisture_15cm, found_stations, missing_stations
    
    if "STATION" not in weather_data:
        logger.error("Weather API response missing STATION data")
        missing_stations.extend([SOIL_MOISTURE_STATION_ID, WEATHER_STATION_ID])
        return air_temp, relative_humidity, wind_speed, soil_moisture_15cm, found_stations, missing_stations
    
    stations = weather_data["STATION"]
    
    # Check if we received data for expected stations
    station_ids_in_response = [station.get("STID") for station in stations]
    logger.info(f"Received data for stations: {station_ids_in_response}")
    
    if SOIL_MOISTURE_STATION_ID not in station_ids_in_response:
        missing_stations.append(SOIL_MOISTURE_STATION_ID)
    
    if WEATHER_STATION_ID not in station_ids_in_response:
        missing_stations.append(WEATHER_STATION_ID)
    
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
            # For CEYC1: Get temperature, humidity, and wind data
            air_temp = observations.get("air_temp_value_1", {}).get("value")
            relative_humidity = observations.get("relative_humidity_value_1", {}).get("value")
            wind_speed = observations.get("wind_speed_value_1", {}).get("value")
    
    return air_temp, relative_humidity, wind_speed, soil_moisture_15cm, found_stations, missing_stations

def process_wunderground_data(wunderground_data: Optional[Dict[str, Any]]) -> Tuple[Optional[float], List[str], List[str]]:
    """Process Weather Underground API response to extract wind gust data.
    
    Args:
        wunderground_data: The response from the Weather Underground API
        
    Returns:
        Tuple of (wind_gust, found_stations, missing_stations)
    """
    wind_gust = None
    found_stations = []
    missing_stations = []
    
    if not wunderground_data:
        logger.error("Failed to get Weather Underground data")
        missing_stations.append(WUNDERGROUND_STATION_ID)
        return wind_gust, found_stations, missing_stations
    
    try:
        # Extract wind gust data from the response
        observations = wunderground_data.get("observations", [])
        if observations and len(observations) > 0:
            # The first observation contains the current conditions
            current = observations[0]
            wind_gust = current.get("imperial", {}).get("windGust")
            found_stations.append(WUNDERGROUND_STATION_ID)
            logger.info(f"Found wind gust data: {wind_gust} mph from station {WUNDERGROUND_STATION_ID}")
        else:
            missing_stations.append(WUNDERGROUND_STATION_ID)
    except Exception as e:
        logger.error(f"Error processing Weather Underground data: {str(e)}")
        missing_stations.append(WUNDERGROUND_STATION_ID)
    
    return wind_gust, found_stations, missing_stations

def combine_weather_data(
    synoptic_data: Optional[Dict[str, Any]], 
    wunderground_data: Optional[Dict[str, Any]],
    cached_fields: Dict[str, bool] = None
) -> Dict[str, Any]:
    """Combine data from Synoptic and Weather Underground APIs.
    
    Args:
        synoptic_data: The response from the Synoptic API
        wunderground_data: The response from the Weather Underground API
        cached_fields: Dictionary tracking which fields are using cached data
        
    Returns:
        Dictionary containing combined weather data
    """
    # Process Synoptic data
    air_temp, relative_humidity, wind_speed, soil_moisture_15cm, synoptic_found, synoptic_missing = process_synoptic_data(synoptic_data)
    
    # Process Weather Underground data
    wind_gust, wunderground_found, wunderground_missing = process_wunderground_data(wunderground_data)
    
    # Combine the data from all stations
    found_stations = synoptic_found + wunderground_found
    missing_stations = synoptic_missing + wunderground_missing
    
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
        data_issues.append(f"Wind gust data missing from station {WUNDERGROUND_STATION_ID}")
    
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
            "wind_gust_station": WUNDERGROUND_STATION_ID
        },
        "data_status": {
            "found_stations": found_stations,
            "missing_stations": missing_stations,
            "issues": data_issues
        },
        # Use timezone-aware datetime
        "cache_timestamp": datetime.now(TIMEZONE).isoformat()
    }
    
    # Add cached_fields if provided
    if cached_fields:
        latest_weather["cached_fields"] = cached_fields
    
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

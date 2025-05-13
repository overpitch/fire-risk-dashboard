from typing import Dict, Any, Tuple, Optional
from config import (
    THRESH_TEMP_CELSIUS, THRESH_HUMID, THRESH_WIND, 
    THRESH_GUSTS, THRESH_SOIL_MOIST, logger
)

# Mapping from session override keys to internal weather data keys
OVERRIDE_KEY_MAP = {
    "temperature": "air_temp",
    "humidity": "relative_humidity",
    "average_winds": "wind_speed", # As per admin_endpoints.py and JS
    "wind_gust": "wind_gust",
    "soil_moisture": "soil_moisture_15cm" # As per admin_endpoints.py and JS
}

def calculate_fire_risk(
    weather: Dict[str, Any], 
    manual_overrides: Optional[Dict[str, float]] = None
) -> Tuple[str, str]:
    """Determines fire risk level based on weather data and environmental thresholds,
    applying manual overrides if provided.
    
    Args:
        weather: Dictionary containing weather data with keys for air_temp, 
                 relative_humidity, wind_speed, wind_gust, and soil_moisture_15cm.
        manual_overrides: Optional dictionary where keys are metric names 
                          (e.g., "temperature", "humidity") and values are the 
                          overridden numerical values.
    
    Returns:
        Tuple of (risk_level, explanation) where risk_level is "Red" or "Orange"
    """
    try:
        # Get initial values from the weather data
        air_temp_val = weather.get("air_temp")
        relative_humidity_val = weather.get("relative_humidity")
        wind_speed_val = weather.get("wind_speed")
        wind_gust_val = weather.get("wind_gust")
        soil_moisture_15cm_val = weather.get("soil_moisture_15cm")

        # Log original received values
        logger.info(f"Original weather data: temp={air_temp_val}°C, humidity={relative_humidity_val}%, "
                    f"wind={wind_speed_val}mph, gusts={wind_gust_val}mph, soil={soil_moisture_15cm_val}%")

        applied_overrides_log = []
        if manual_overrides:
            logger.info(f"Applying manual overrides: {manual_overrides}")
            if "temperature" in manual_overrides and manual_overrides["temperature"] is not None:
                temp_override_f = manual_overrides["temperature"]
                # Convert Fahrenheit override to Celsius for internal calculation
                air_temp_val = (temp_override_f - 32) * 5/9
                applied_overrides_log.append(f"temp={air_temp_val:.2f}°C (override from {temp_override_f}°F)")
            if "humidity" in manual_overrides and manual_overrides["humidity"] is not None:
                relative_humidity_val = manual_overrides["humidity"]
                applied_overrides_log.append(f"humidity={relative_humidity_val}% (override)")
            if "average_winds" in manual_overrides and manual_overrides["average_winds"] is not None:
                wind_speed_val = manual_overrides["average_winds"]
                applied_overrides_log.append(f"wind={wind_speed_val}mph (override)")
            if "wind_gust" in manual_overrides and manual_overrides["wind_gust"] is not None:
                wind_gust_val = manual_overrides["wind_gust"]
                applied_overrides_log.append(f"gusts={wind_gust_val}mph (override)")
            if "soil_moisture" in manual_overrides and manual_overrides["soil_moisture"] is not None:
                soil_moisture_15cm_val = manual_overrides["soil_moisture"]
                applied_overrides_log.append(f"soil={soil_moisture_15cm_val}% (override)")
        
        if applied_overrides_log:
            logger.info(f"Values after overrides: {', '.join(applied_overrides_log)}")
        
        # Use defaults if values are None (after potential overrides)
        temp = float(0 if air_temp_val is None else air_temp_val)
        humidity = float(100 if relative_humidity_val is None else relative_humidity_val)
        wind = float(0 if wind_speed_val is None else wind_speed_val)
        gusts = float(0 if wind_gust_val is None else wind_gust_val)
        soil = float(100 if soil_moisture_15cm_val is None else soil_moisture_15cm_val)
        
        # Log the final values used for calculation
        logger.info(f"Calculating risk with: temp={temp}°C, humidity={humidity}%, "
                    f"wind={wind}mph, gusts={gusts}mph, soil={soil}%")

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

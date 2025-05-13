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
) -> Tuple[str, str, Dict[str, Any]]:
    """Determines fire risk level based on weather data and environmental thresholds,
    applying manual overrides if provided.
    
    Args:
        weather: Dictionary containing weather data with keys for air_temp (Celsius), 
                 relative_humidity, wind_speed (mph), wind_gust (mph), and soil_moisture_15cm.
        manual_overrides: Optional dictionary where keys are metric names 
                          (e.g., "temperature" in F, "humidity") and values are the 
                          overridden numerical values.
    
    Returns:
        Tuple of (risk_level, explanation, effective_weather_values) 
        where risk_level is "Red" or "Orange", and effective_weather_values
        contains the values used for calculation, with temperature in Fahrenheit.
    """
    try:
        # Initialize effective values with original weather data (converting temp to F if needed)
        # Note: weather["air_temp"] is expected to be in Celsius from API/combine_weather_data
        original_temp_c = weather.get("air_temp")
        original_temp_f = (original_temp_c * 9/5) + 32 if original_temp_c is not None else None

        effective_values = {
            "temperature": original_temp_f, # Store as F for display
            "humidity": weather.get("relative_humidity"),
            "wind_speed": weather.get("wind_speed"),
            "wind_gust": weather.get("wind_gust"),
            "soil_moisture": weather.get("soil_moisture_15cm")
        }

        # Values for calculation (temp will be in Celsius)
        air_temp_c_calc = original_temp_c
        humidity_calc = effective_values["humidity"]
        wind_speed_calc = effective_values["wind_speed"]
        wind_gust_calc = effective_values["wind_gust"]
        soil_moisture_calc = effective_values["soil_moisture"]

        logger.info(f"Original weather data: temp={air_temp_c_calc}°C, humidity={humidity_calc}%, "
                    f"wind={wind_speed_calc}mph, gusts={wind_gust_calc}mph, soil={soil_moisture_calc}%")

        applied_overrides_log = []
        if manual_overrides:
            logger.info(f"Applying manual overrides: {manual_overrides}")
            if "temperature" in manual_overrides and manual_overrides["temperature"] is not None:
                temp_override_f = manual_overrides["temperature"]
                effective_values["temperature"] = temp_override_f # Store F for display
                air_temp_c_calc = (temp_override_f - 32) * 5/9    # Convert F override to C for calculation
                applied_overrides_log.append(f"temp={air_temp_c_calc:.2f}°C (override from {temp_override_f}°F)")
            
            if "humidity" in manual_overrides and manual_overrides["humidity"] is not None:
                humidity_calc = manual_overrides["humidity"]
                effective_values["humidity"] = humidity_calc
                applied_overrides_log.append(f"humidity={humidity_calc}% (override)")

            if "average_winds" in manual_overrides and manual_overrides["average_winds"] is not None:
                wind_speed_calc = manual_overrides["average_winds"]
                effective_values["wind_speed"] = wind_speed_calc
                applied_overrides_log.append(f"wind={wind_speed_calc}mph (override)")

            if "wind_gust" in manual_overrides and manual_overrides["wind_gust"] is not None:
                wind_gust_calc = manual_overrides["wind_gust"]
                effective_values["wind_gust"] = wind_gust_calc
                applied_overrides_log.append(f"gusts={wind_gust_calc}mph (override)")

            if "soil_moisture" in manual_overrides and manual_overrides["soil_moisture"] is not None:
                soil_moisture_calc = manual_overrides["soil_moisture"]
                effective_values["soil_moisture"] = soil_moisture_calc
                applied_overrides_log.append(f"soil={soil_moisture_calc}% (override)")
        
        if applied_overrides_log:
            logger.info(f"Values after overrides: {', '.join(applied_overrides_log)}")
        
        # Use defaults if values are None (after potential overrides) for calculation variables
        temp_c_for_logic = float(0 if air_temp_c_calc is None else air_temp_c_calc)
        humidity_for_logic = float(100 if humidity_calc is None else humidity_calc)
        wind_for_logic = float(0 if wind_speed_calc is None else wind_speed_calc)
        gusts_for_logic = float(0 if wind_gust_calc is None else wind_gust_calc)
        soil_for_logic = float(100 if soil_moisture_calc is None else soil_moisture_calc)
        
        # Update effective_values with defaulted values if they were None, for completeness in return
        # Temperature in effective_values is already F or overridden F.
        # Others are direct.
        effective_values["humidity"] = humidity_for_logic if effective_values["humidity"] is None else effective_values["humidity"]
        effective_values["wind_speed"] = wind_for_logic if effective_values["wind_speed"] is None else effective_values["wind_speed"]
        effective_values["wind_gust"] = gusts_for_logic if effective_values["wind_gust"] is None else effective_values["wind_gust"]
        effective_values["soil_moisture"] = soil_for_logic if effective_values["soil_moisture"] is None else effective_values["soil_moisture"]
        if effective_values["temperature"] is None and original_temp_f is None: # If temp was None and no override
             effective_values["temperature"] = (temp_c_for_logic * 9/5) + 32 # Default 0C to 32F

        logger.info(f"Calculating risk with: temp={temp_c_for_logic}°C, humidity={humidity_for_logic}%, "
                    f"wind={wind_for_logic}mph, gusts={gusts_for_logic}mph, soil={soil_for_logic}%")

        # Check if all thresholds are exceeded
        temp_exceeded = temp_c_for_logic > THRESH_TEMP_CELSIUS
        humidity_exceeded = humidity_for_logic < THRESH_HUMID
        wind_exceeded = wind_for_logic > THRESH_WIND
        gusts_exceeded = gusts_for_logic > THRESH_GUSTS
        soil_exceeded = soil_for_logic < THRESH_SOIL_MOIST
        
        # Log threshold checks
        logger.info(f"Threshold checks: temp={temp_exceeded}, humidity={humidity_exceeded}, "
                    f"wind={wind_exceeded}, gusts={gusts_exceeded}, soil={soil_exceeded}")
        
        risk_level = "Orange"
        explanation = "Low or Moderate Fire Risk. Exercise standard prevention practices."

        if temp_exceeded and humidity_exceeded and wind_exceeded and gusts_exceeded and soil_exceeded:
            risk_level = "Red"
            explanation = "High fire risk due to high temperature, low humidity, strong winds, high wind gusts, and low soil moisture."
        
        # Round temperature in effective_values for cleaner display if it's a float
        if effective_values["temperature"] is not None:
            effective_values["temperature"] = round(effective_values["temperature"])


        return risk_level, explanation, effective_values

    except Exception as e:
        logger.error(f"Error calculating fire risk: {str(e)}")
        # Return a default structure for effective_values in case of error
        default_effective_values = {
            "temperature": None, "humidity": None, "wind_speed": None,
            "wind_gust": None, "soil_moisture": None
        }
        return "Error", f"Could not calculate risk: {str(e)}", default_effective_values

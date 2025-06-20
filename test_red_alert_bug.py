#!/usr/bin/env python3
"""
Test script to reproduce the red alert bug where all five weather criteria 
exceed thresholds but the banner doesn't turn red and no emails are sent.
"""

import asyncio
import sys
import os
from datetime import datetime

# Add the current directory to Python path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fire_risk_logic import calculate_fire_risk
from cache import data_cache
from cache_refresh import refresh_data_cache
from config import logger, THRESH_TEMP, THRESH_HUMID, THRESH_WIND, THRESH_GUSTS, THRESH_SOIL_MOIST

def test_fire_risk_calculation():
    """Test the fire risk calculation with values that should trigger red alert."""
    
    print("🔥 TESTING FIRE RISK CALCULATION BUG")
    print("=" * 50)
    
    # Create weather data where ALL five criteria exceed thresholds
    # Based on the thresholds from config.py:
    # THRESH_TEMP = 75°F (23.9°C)
    # THRESH_HUMID = 15%
    # THRESH_WIND = 15 mph
    # THRESH_GUSTS = 20 mph
    # THRESH_SOIL_MOIST = 10%
    
    print(f"Current thresholds:")
    print(f"  Temperature: >{THRESH_TEMP}°F")
    print(f"  Humidity: <{THRESH_HUMID}%")
    print(f"  Wind Speed: >{THRESH_WIND} mph")
    print(f"  Wind Gusts: >{THRESH_GUSTS} mph")
    print(f"  Soil Moisture: <{THRESH_SOIL_MOIST}%")
    print()
    
    # Create test weather data that EXCEEDS all thresholds
    test_weather = {
        "air_temp": 32.0,  # 32°C = 89.6°F (exceeds 75°F threshold)
        "relative_humidity": 9.0,  # 9% (below 15% threshold)
        "wind_speed": 25.0,  # 25 mph (exceeds 15 mph threshold)
        "wind_gust": 35.0,  # 35 mph (exceeds 20 mph threshold)
        "soil_moisture_15cm": 5.0  # 5% (below 10% threshold)
    }
    
    print(f"Test weather data (should trigger RED alert):")
    print(f"  Temperature: {test_weather['air_temp']}°C ({test_weather['air_temp'] * 9/5 + 32:.1f}°F)")
    print(f"  Humidity: {test_weather['relative_humidity']}%")
    print(f"  Wind Speed: {test_weather['wind_speed']} mph")
    print(f"  Wind Gusts: {test_weather['wind_gust']} mph")
    print(f"  Soil Moisture: {test_weather['soil_moisture_15cm']}%")
    print()
    
    # Test without manual overrides first
    print("🧪 Testing without manual overrides...")
    risk_level, explanation, effective_values = calculate_fire_risk(test_weather)
    
    print(f"RESULT:")
    print(f"  Risk Level: {risk_level}")
    print(f"  Explanation: {explanation}")
    print(f"  Effective Values: {effective_values}")
    print()
    
    # Check if the result is correct
    expected_risk = "Red"
    if risk_level == expected_risk:
        print("✅ SUCCESS: Risk level correctly calculated as Red")
    else:
        print(f"❌ FAILURE: Expected '{expected_risk}' but got '{risk_level}'")
        print("🐛 BUG CONFIRMED: Fire risk calculation is not working correctly!")
    
    print()
    
    # Test with manual overrides (simulating admin test conditions)
    print("🧪 Testing with manual overrides (simulating admin test)...")
    manual_overrides = {
        "temperature": 90.0,  # 90°F (exceeds 75°F threshold)
        "humidity": 10.0,     # 10% (below 15% threshold)
        "average_winds": 20.0, # 20 mph (exceeds 15 mph threshold)
        "wind_gust": 30.0,    # 30 mph (exceeds 20 mph threshold)
        "soil_moisture": 8.0  # 8% (below 10% threshold)
    }
    
    print(f"Manual overrides:")
    for key, value in manual_overrides.items():
        print(f"  {key}: {value}")
    print()
    
    risk_level_override, explanation_override, effective_values_override = calculate_fire_risk(
        test_weather, manual_overrides=manual_overrides
    )
    
    print(f"RESULT WITH OVERRIDES:")
    print(f"  Risk Level: {risk_level_override}")
    print(f"  Explanation: {explanation_override}")
    print(f"  Effective Values: {effective_values_override}")
    print()
    
    # Check if the result is correct with overrides
    if risk_level_override == expected_risk:
        print("✅ SUCCESS: Risk level correctly calculated as Red with overrides")
    else:
        print(f"❌ FAILURE: Expected '{expected_risk}' but got '{risk_level_override}' with overrides")
        print("🐛 BUG CONFIRMED: Fire risk calculation with overrides is not working correctly!")
    
    return risk_level == expected_risk and risk_level_override == expected_risk

async def test_email_alert_logic():
    """Test the email alert logic to see if it would trigger."""
    
    print("\n🚨 TESTING EMAIL ALERT LOGIC")
    print("=" * 50)
    
    # Set up the cache state to simulate an Orange -> Red transition
    print("Setting up cache state for Orange -> Red transition...")
    
    # Set previous risk level to Orange
    data_cache.previous_risk_level = "Orange"
    data_cache.risk_level_timestamp = datetime.now()
    data_cache.last_alerted_timestamp = None  # No previous alert
    
    print(f"  Previous risk level: {data_cache.previous_risk_level}")
    print(f"  Risk level timestamp: {data_cache.risk_level_timestamp}")
    print(f"  Last alerted timestamp: {data_cache.last_alerted_timestamp}")
    print()
    
    # Test the should_send_alert_for_transition logic
    current_risk = "Red"
    should_send = data_cache.should_send_alert_for_transition(current_risk, ignore_daily_limit=False)
    
    print(f"Testing should_send_alert_for_transition('{current_risk}', ignore_daily_limit=False):")
    print(f"  Result: {should_send}")
    
    if should_send:
        print("✅ SUCCESS: Email alert logic would trigger")
    else:
        print("❌ FAILURE: Email alert logic would NOT trigger")
        print("🐛 BUG CONFIRMED: Email alert logic is not working correctly!")
    
    print()
    
    # Test with ignore_daily_limit=True
    should_send_ignore = data_cache.should_send_alert_for_transition(current_risk, ignore_daily_limit=True)
    print(f"Testing should_send_alert_for_transition('{current_risk}', ignore_daily_limit=True):")
    print(f"  Result: {should_send_ignore}")
    
    return should_send

def main():
    """Run all tests to diagnose the red alert bug."""
    
    print("🚨 FIRE WEATHER RED ALERT BUG DIAGNOSIS")
    print("=" * 60)
    print()
    
    # Test 1: Fire risk calculation
    calculation_works = test_fire_risk_calculation()
    
    # Test 2: Email alert logic
    alert_logic_works = asyncio.run(test_email_alert_logic())
    
    # Summary
    print("\n📊 DIAGNOSIS SUMMARY")
    print("=" * 30)
    print(f"Fire risk calculation works: {calculation_works}")
    print(f"Email alert logic works: {alert_logic_works}")
    print()
    
    if calculation_works and alert_logic_works:
        print("✅ Both systems appear to be working correctly.")
        print("🤔 The bug may be in the integration between these systems or in the frontend display.")
    elif not calculation_works:
        print("❌ BUG FOUND: Fire risk calculation is failing!")
        print("🔧 Check the threshold comparison logic in fire_risk_logic.py")
    elif not alert_logic_works:
        print("❌ BUG FOUND: Email alert logic is failing!")
        print("🔧 Check the should_send_alert_for_transition logic in cache.py")
    else:
        print("❌ Both systems are failing!")
        print("🔧 Multiple bugs detected - start with fire risk calculation")
    
    print()
    print("💡 Next steps:")
    print("1. Run the server and check the enhanced logging output")
    print("2. Use the admin test conditions feature to reproduce the bug")
    print("3. Check server logs for the detailed diagnostic messages")

if __name__ == "__main__":
    main()

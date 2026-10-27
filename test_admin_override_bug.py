#!/usr/bin/env python3
"""
Test script to reproduce the red alert bug using admin test conditions.
This simulates the exact scenario where all five criteria exceed thresholds.
"""

import os
import requests
import json
import sys

def test_admin_override_scenario():
    """Test the admin override scenario where all five criteria exceed thresholds."""
    
    print("🔧 TESTING ADMIN OVERRIDE SCENARIO")
    print("=" * 50)
    
    # First, log in with ADMIN_PASSWORD and get a session token
    print("Step 1: Authenticating with admin...")
    
    try:
        password = os.getenv("ADMIN_PASSWORD")
        if not password:
            print("❌ Set the ADMIN_PASSWORD environment variable to run this script")
            return False

        login_response = requests.post(
            "http://localhost:8000/admin/validate-password",
            json={"password": password},
            timeout=10
        )
        
        if login_response.status_code != 200:
            print(f"❌ Login failed: {login_response.status_code}")
            return False
            
        login_data = login_response.json()
        if not login_data.get("valid"):
            print(f"❌ Invalid password: {login_data.get('error', 'Unknown error')}")
            return False
            
        # The server sets the session as a cookie rather than returning it in the body
        session_token = login_response.cookies.get("session_token")
        print(f"✅ Admin authenticated successfully")
        
        # Step 2: Set test conditions that exceed ALL thresholds
        print("\nStep 2: Setting test conditions that exceed ALL thresholds...")
        
        test_conditions = {
            "temperature": 90.0,      # >75°F threshold
            "humidity": 10.0,         # <15% threshold  
            "average_winds": 20.0,    # >10 mph threshold
            "wind_gust": 25.0,        # >15 mph threshold
            "soil_moisture": 5.0      # <10% threshold
        }
        
        print("Setting test conditions:")
        for key, value in test_conditions.items():
            print(f"  {key}: {value}")
        
        # Set the test conditions
        conditions_response = requests.post(
            "http://localhost:8000/admin/test-conditions",
            json=test_conditions,
            cookies={"session_token": session_token},
            timeout=10
        )
        
        if conditions_response.status_code != 200:
            print(f"❌ Failed to set test conditions: {conditions_response.status_code}")
            print(f"Response: {conditions_response.text}")
            return False
            
        conditions_data = conditions_response.json()
        print(f"✅ Test conditions set successfully")
        print(f"Updated overrides: {conditions_data.get('updated_overrides', {})}")
        
        # Step 3: Test the fire-risk endpoint with admin session
        print("\nStep 3: Testing fire-risk endpoint with admin overrides...")
        
        # Make request with session token to apply overrides
        risk_response = requests.get(
            "http://localhost:8000/fire-risk?wait_for_fresh=true",
            cookies={"session_token": session_token},
            timeout=30
        )
        
        if risk_response.status_code != 200:
            print(f"❌ Fire risk request failed: {risk_response.status_code}")
            print(f"Response: {risk_response.text}")
            return False
            
        risk_data = risk_response.json()
        
        print("✅ Fire risk response received")
        print(f"Risk Level: {risk_data.get('risk', 'N/A')}")
        print(f"Explanation: {risk_data.get('explanation', 'N/A')}")
        
        # Step 4: Analyze the results
        print("\nStep 4: Analyzing results...")
        
        # Check if all conditions should trigger red alert
        if "thresholds" in risk_data and "weather" in risk_data:
            thresholds = risk_data["thresholds"]
            weather = risk_data["weather"]
            
            print("\n🔍 Threshold Analysis with Admin Overrides:")
            
            # The weather data should reflect the overrides
            temp_c = weather.get("air_temp")
            temp_f = (temp_c * 9/5) + 32 if temp_c is not None else None
            
            print(f"  Temperature: {temp_f:.1f}°F > {thresholds['temp']}°F = {temp_f > thresholds['temp'] if temp_f else 'N/A'}")
            print(f"  Humidity: {weather.get('relative_humidity')}% < {thresholds['humid']}% = {weather.get('relative_humidity') < thresholds['humid'] if weather.get('relative_humidity') else 'N/A'}")
            print(f"  Wind Speed: {weather.get('wind_speed')} mph > {thresholds['wind']} mph = {weather.get('wind_speed') > thresholds['wind'] if weather.get('wind_speed') else 'N/A'}")
            print(f"  Wind Gusts: {weather.get('wind_gust')} mph > {thresholds['gusts']} mph = {weather.get('wind_gust') > thresholds['gusts'] if weather.get('wind_gust') else 'N/A'}")
            print(f"  Soil Moisture: {weather.get('soil_moisture_15cm')}% < {thresholds['soil_moist']}% = {weather.get('soil_moisture_15cm') < thresholds['soil_moist'] if weather.get('soil_moisture_15cm') else 'N/A'}")
            
            # Check if all conditions are met
            all_conditions = []
            if temp_f and thresholds.get('temp'):
                all_conditions.append(temp_f > thresholds['temp'])
            if weather.get('relative_humidity') is not None and thresholds.get('humid'):
                all_conditions.append(weather.get('relative_humidity') < thresholds['humid'])
            if weather.get('wind_speed') is not None and thresholds.get('wind'):
                all_conditions.append(weather.get('wind_speed') > thresholds['wind'])
            if weather.get('wind_gust') is not None and thresholds.get('gusts'):
                all_conditions.append(weather.get('wind_gust') > thresholds['gusts'])
            if weather.get('soil_moisture_15cm') is not None and thresholds.get('soil_moist'):
                all_conditions.append(weather.get('soil_moisture_15cm') < thresholds['soil_moist'])
            
            if all_conditions:
                all_met = all(all_conditions)
                print(f"\n🚨 All conditions met for RED alert: {all_met}")
                print(f"   But API returned risk level: {risk_data.get('risk', 'N/A')}")
                
                if all_met and risk_data.get('risk') != 'Red':
                    print("🐛 BUG CONFIRMED: All conditions met but risk level is not Red!")
                    print("   This explains why the banner didn't turn red and no emails were sent!")
                elif not all_met and risk_data.get('risk') == 'Red':
                    print("🤔 UNEXPECTED: Risk level is Red but not all conditions are met")
                else:
                    print("✅ Risk level matches threshold analysis")
        
        # Step 5: Clean up - clear test conditions
        print("\nStep 5: Cleaning up test conditions...")
        
        cleanup_response = requests.delete(
            "http://localhost:8000/admin/test-conditions",
            cookies={"session_token": session_token},
            timeout=10
        )
        
        if cleanup_response.status_code == 200:
            print("✅ Test conditions cleared successfully")
        else:
            print(f"⚠️ Failed to clear test conditions: {cleanup_response.status_code}")
        
        # Save full response for debugging
        with open('admin_override_debug.json', 'w') as f:
            json.dump(risk_data, f, indent=2)
        print("💾 Full API response saved to admin_override_debug.json")
        
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server. Make sure the server is running on localhost:8000")
        return False
    except Exception as e:
        print(f"❌ Error testing admin override scenario: {e}")
        return False

def main():
    """Run the admin override test."""
    success = test_admin_override_scenario()
    
    if not success:
        print("\n💡 Make sure:")
        print("   1. Server is running: uvicorn main:app --host 0.0.0.0 --port 8000 --reload")
        print("   2. Update the PIN in this script if needed")
        sys.exit(1)

if __name__ == "__main__":
    main()

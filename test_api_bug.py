#!/usr/bin/env python3
"""
Test script to call the actual API and reproduce the red alert bug.
"""

import requests
import json
import sys

def test_api_response():
    """Test the actual API response to see what thresholds are being sent."""
    
    print("🌐 TESTING ACTUAL API RESPONSE")
    print("=" * 50)
    
    try:
        # Test the fire-risk endpoint
        response = requests.get("http://localhost:8000/fire-risk", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            print("✅ API Response received successfully")
            print(f"Risk Level: {data.get('risk', 'N/A')}")
            print(f"Explanation: {data.get('explanation', 'N/A')}")
            print()
            
            # Check thresholds
            if "thresholds" in data:
                thresholds = data["thresholds"]
                print("📊 Thresholds from API:")
                print(f"  Temperature: >{thresholds.get('temp', 'N/A')}°F")
                print(f"  Humidity: <{thresholds.get('humid', 'N/A')}%")
                print(f"  Wind Speed: >{thresholds.get('wind', 'N/A')} mph")
                print(f"  Wind Gusts: >{thresholds.get('gusts', 'N/A')} mph")
                print(f"  Soil Moisture: <{thresholds.get('soil_moist', 'N/A')}%")
            else:
                print("❌ No thresholds found in API response!")
            
            print()
            
            # Check weather data
            if "weather" in data:
                weather = data["weather"]
                print("🌤️ Current Weather Data:")
                
                # Convert temperature to Fahrenheit if it's in Celsius
                temp_c = weather.get("air_temp")
                temp_f = (temp_c * 9/5) + 32 if temp_c is not None else None
                
                print(f"  Temperature: {temp_c}°C ({temp_f:.1f}°F)" if temp_c else "  Temperature: N/A")
                print(f"  Humidity: {weather.get('relative_humidity', 'N/A')}%")
                print(f"  Wind Speed: {weather.get('wind_speed', 'N/A')} mph")
                print(f"  Wind Gusts: {weather.get('wind_gust', 'N/A')} mph")
                print(f"  Soil Moisture: {weather.get('soil_moisture_15cm', 'N/A')}%")
                
                print()
                
                # Check if values exceed thresholds (using API thresholds)
                if "thresholds" in data:
                    thresholds = data["thresholds"]
                    
                    print("🔍 Threshold Analysis:")
                    
                    # Temperature check
                    if temp_f and thresholds.get('temp'):
                        temp_exceeds = temp_f > thresholds['temp']
                        print(f"  Temperature: {temp_f:.1f}°F > {thresholds['temp']}°F = {temp_exceeds}")
                    
                    # Humidity check
                    humidity = weather.get('relative_humidity')
                    if humidity and thresholds.get('humid'):
                        humid_exceeds = humidity < thresholds['humid']
                        print(f"  Humidity: {humidity}% < {thresholds['humid']}% = {humid_exceeds}")
                    
                    # Wind speed check
                    wind_speed = weather.get('wind_speed')
                    if wind_speed and thresholds.get('wind'):
                        wind_exceeds = wind_speed > thresholds['wind']
                        print(f"  Wind Speed: {wind_speed} mph > {thresholds['wind']} mph = {wind_exceeds}")
                    
                    # Wind gust check
                    wind_gust = weather.get('wind_gust')
                    if wind_gust and thresholds.get('gusts'):
                        gust_exceeds = wind_gust > thresholds['gusts']
                        print(f"  Wind Gusts: {wind_gust} mph > {thresholds['gusts']} mph = {gust_exceeds}")
                    
                    # Soil moisture check
                    soil_moisture = weather.get('soil_moisture_15cm')
                    if soil_moisture and thresholds.get('soil_moist'):
                        soil_exceeds = soil_moisture < thresholds['soil_moist']
                        print(f"  Soil Moisture: {soil_moisture}% < {thresholds['soil_moist']}% = {soil_exceeds}")
                    
                    print()
                    
                    # Check if all conditions are met for red alert
                    all_conditions = []
                    if temp_f and thresholds.get('temp'):
                        all_conditions.append(temp_f > thresholds['temp'])
                    if humidity and thresholds.get('humid'):
                        all_conditions.append(humidity < thresholds['humid'])
                    if wind_speed and thresholds.get('wind'):
                        all_conditions.append(wind_speed > thresholds['wind'])
                    if wind_gust and thresholds.get('gusts'):
                        all_conditions.append(wind_gust > thresholds['gusts'])
                    if soil_moisture and thresholds.get('soil_moist'):
                        all_conditions.append(soil_moisture < thresholds['soil_moist'])
                    
                    if all_conditions:
                        all_met = all(all_conditions)
                        print(f"🚨 All conditions met for RED alert: {all_met}")
                        print(f"   But API returned risk level: {data.get('risk', 'N/A')}")
                        
                        if all_met and data.get('risk') != 'Red':
                            print("🐛 BUG CONFIRMED: All conditions met but risk level is not Red!")
                        elif not all_met and data.get('risk') == 'Red':
                            print("🤔 UNEXPECTED: Risk level is Red but not all conditions are met")
                        else:
                            print("✅ Risk level matches threshold analysis")
            
            # Save full response for debugging
            with open('api_response_debug.json', 'w') as f:
                json.dump(data, f, indent=2)
            print("💾 Full API response saved to api_response_debug.json")
            
            return True
            
        else:
            print(f"❌ API request failed with status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server. Make sure the server is running on localhost:8000")
        return False
    except Exception as e:
        print(f"❌ Error testing API: {e}")
        return False

def main():
    """Run the API test."""
    success = test_api_response()
    
    if not success:
        print("\n💡 Make sure to start the server first:")
        print("   python main.py")
        sys.exit(1)

if __name__ == "__main__":
    main()

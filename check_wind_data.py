import requests
import json
from config import SYNOPTIC_API_KEY, SYNOPTIC_BASE_URL, WIND_STATION_ID

def get_current_wind_data():
    # Get API token
    token_url = f"{SYNOPTIC_BASE_URL}/auth?apikey={SYNOPTIC_API_KEY}"
    try:
        token_response = requests.get(token_url)
        token_data = token_response.json()
        token = token_data.get("TOKEN")
        
        if not token:
            print("Failed to get API token")
            return
        
        # Get wind station data
        station_url = f"{SYNOPTIC_BASE_URL}/stations/latest?stid={WIND_STATION_ID}&token={token}"
        response = requests.get(station_url)
        data = response.json()
        
        print(f"Station: {WIND_STATION_ID}")
        
        if 'STATION' in data and data['STATION']:
            station = data['STATION'][0]
            observations = station.get('OBSERVATIONS', {})
            
            # Wind speed
            wind_speed_data = observations.get('wind_speed_value_1', {})
            wind_speed = wind_speed_data.get('value')
            wind_speed_timestamp = wind_speed_data.get('date_time')
            
            # Wind gust
            wind_gust_data = observations.get('wind_gust_value_1', {})
            wind_gust = wind_gust_data.get('value')
            wind_gust_timestamp = wind_gust_data.get('date_time')
            
            # Convert from m/s to mph if values exist
            wind_speed_mph = wind_speed * 2.237 if wind_speed is not None else None
            wind_gust_mph = wind_gust * 2.237 if wind_gust is not None else None
            
            print(f"Wind Speed: {wind_speed} m/s ({wind_speed_mph:.1f} mph)")
            print(f"Wind Gust: {wind_gust} m/s ({wind_gust_mph:.1f} mph)")
            print(f"Wind Speed Timestamp: {wind_speed_timestamp}")
            print(f"Wind Gust Timestamp: {wind_gust_timestamp}")
        else:
            print("No station data found in response")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_current_wind_data()

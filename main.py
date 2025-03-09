from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import requests
import os

app = FastAPI()

# API Configuration
API_KEY = os.getenv("SYNOPTICDATA_API_KEY", "your_api_key_here")
AUTH_URL = "https://api.synopticdata.com/v2/auth"
BASE_URL = "https://api.synopticdata.com/v2/stations/latest"
STATION_ID = "C3DLA"  # Replace with actual station ID

# Fire risk thresholsd
THRESHOLDS = {
    "red": {"temp": 90, "humidity": 15, "wind": 20},
    "yellow": {"temp": 80, "humidity": 25},
}

def get_api_token():
    """Requests a short-lived authentication token from Synoptic API."""
    response = requests.get(AUTH_URL, params={"apikey": API_KEY}, timeout=10)
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Failed to get authentication token")
    return response.json().get("TOKEN")

def get_weather_data():
    """Fetches latest weather data using an authenticated token."""
    token = get_api_token()  # Get short-lived token
    
    # Print the token being used
    print(f"🔍 Using API Token: {token}")

    params = {
        "token": token,  # Use token instead of API key
        "stid": STATION_ID,
        "vars": "air_temp,relative_humidity,wind_speed",
        "recent": "60",
        "units": "temp|F,speed|mph",
    }

    # Construct the full request URL for debugging
    full_url = f"{BASE_URL}?token={token}&stid={STATION_ID}&vars=air_temp,relative_humidity,wind_speed&recent=60&units=temp|F,speed|mph"
    print(f"🌍 Fetching data from: {full_url}")  # ✅ Print full URL

    response = requests.get(BASE_URL, params=params)
    
    # Print the API response
    print("📡 API Response Status:", response.status_code)  # ✅ Print status code
    print("📊 API Response JSON:", response.json())  # ✅ Print full JSON response

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch weather data")

    return response.json()

def calculate_fire_risk(weather):
    """Determines fire risk level based on thresholds."""
    temp = weather["air_temp"]
    humidity = weather["relative_humidity"]
    wind = weather["wind_speed"]

    if temp > THRESHOLDS["red"]["temp"] and humidity < THRESHOLDS["red"]["humidity"] and wind > THRESHOLDS["red"]["wind"]:
        return "Red", "High fire risk due to high temp, low humidity, and strong winds."
    elif temp > THRESHOLDS["yellow"]["temp"] and humidity < THRESHOLDS["yellow"]["humidity"]:
        return "Yellow", "Moderate fire risk."
    else:
        return "Green", "Low fire risk."

@app.get("/fire-risk")
def fire_risk():
    """API endpoint to fetch fire risk status."""
    weather_data = get_weather_data()
    
    # Extract latest weather values
    latest_weather = {
        "air_temp": weather_data["STATION"][0]["OBSERVATIONS"]["air_temp_value_1"]["value"],
        "relative_humidity": weather_data["STATION"][0]["OBSERVATIONS"]["relative_humidity_value_1"]["value"],
        "wind_speed": weather_data["STATION"][0]["OBSERVATIONS"]["wind_speed_value_1"]["value"],
    }
    
    risk, explanation = calculate_fire_risk(latest_weather)
    return {"risk": risk, "explanation": explanation, "weather": latest_weather}

@app.get("/", response_class=HTMLResponse)
def home():
    """Bootstrap-based Fire Risk Dashboard."""
    return """
    <!DOCTYPE html>
    <html lang='en'>
    <head>
        <meta charset='UTF-8'>
        <meta name='viewport' content='width=device-width, initial-scale=1.0'>
        <title>Fire Risk Dashboard</title>
        <link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css' rel='stylesheet'>
    </head>
    <body class='container mt-5'>
        <h1 class='mb-3'>Sierra City Fire Risk Dashboard</h1>
        <div id='fire-risk' class='p-3 text-white'></div>
        <script>
            async function fetchFireRisk() {
                const response = await fetch('/fire-risk');
                const data = await response.json();
                const riskDiv = document.getElementById('fire-risk');
                riskDiv.textContent = `Fire Risk: ${data.risk} - ${data.explanation}`;
                riskDiv.className = `p-3 text-white ${data.risk === 'Red' ? 'bg-danger' : data.risk === 'Yellow' ? 'bg-warning' : 'bg-success'}`;
            }
            fetchFireRisk();
        </script>
    </body>
    </html>
    """
import pytest
import re
from bs4 import BeautifulSoup
from unittest.mock import patch, MagicMock

from main import app, data_cache, refresh_data_cache

@pytest.mark.asyncio
async def test_homepage_loads(client):
    """Test that the homepage loads successfully."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Fire Weather Advisory" in response.title

@pytest.mark.asyncio
async def test_homepage_with_fresh_data(client, reset_cache, populate_cache_with_valid_data):
    """Test that the homepage displays fresh data correctly."""
    # First, populate the cache with valid data
    original_data = populate_cache_with_valid_data
    
    # Get the homepage
    response = client.get("/")
    
    # Check that the response is successful
    assert response.status_code == 200
    
    # Parse the HTML
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Check that the fire risk is displayed
    fire_risk_div = soup.find(id='fire-risk')
    assert fire_risk_div is not None
    
    # Check that the weather details are displayed
    weather_details_div = soup.find(id='weather-details')
    assert weather_details_div is not None
    
    # Check that the JavaScript code for handling cached data is present
    assert 'const isCachedTemp = data.weather.cached_fields && data.weather.cached_fields.temperature;' in response.text
    assert 'const isCachedHumidity = data.weather.cached_fields && data.weather.cached_fields.humidity;' in response.text
    assert 'const isCachedWindSpeed = data.weather.cached_fields && data.weather.cached_fields.wind_speed;' in response.text
    assert 'const isCachedWindGust = data.weather.cached_fields && data.weather.cached_fields.wind_gust;' in response.text
    assert 'const isCachedSoilMoisture = data.weather.cached_fields && data.weather.cached_fields.soil_moisture;' in response.text

@pytest.mark.asyncio
async def test_cached_data_display_in_javascript(client, reset_cache, populate_cache_with_valid_data):
    """Test that the JavaScript code properly handles cached data."""
    # Get the homepage
    response = client.get("/")
    
    # Check that the response is successful
    assert response.status_code == 200
    
    # Check that the JavaScript code for handling cached data is correct
    # For temperature
    temp_js_pattern = r'const tempFahrenheit = tempCelsius \? Math\.round\(\(tempCelsius \* 9/5\) \+ 32\) \+ \'°F\' : \s*\(isCachedTemp \? Math\.round\(\(tempCelsius \* 9/5\) \+ 32\) \+ \'°F \(cached\)\' : \s*\'<span class="unavailable">&lt;unavailable&gt;</span>\'\);'
    assert re.search(temp_js_pattern, response.text, re.DOTALL) is not None
    
    # For humidity
    humidity_js_pattern = r'const humidity = data\.weather\.relative_humidity \? Math\.round\(data\.weather\.relative_humidity\) \+ \'%\' : \s*\(isCachedHumidity \? Math\.round\(data\.weather\.relative_humidity\) \+ \'% \(cached\)\' : \s*\'<span class="unavailable">&lt;unavailable&gt;</span>\'\);'
    assert re.search(humidity_js_pattern, response.text, re.DOTALL) is not None
    
    # For wind speed
    wind_speed_js_pattern = r'const windSpeed = data\.weather\.wind_speed !== null && data\.weather\.wind_speed !== undefined \? \s*Math\.round\(data\.weather\.wind_speed\) \+ \' mph\' : \s*\(isCachedWindSpeed \? Math\.round\(data\.weather\.wind_speed\) \+ \' mph \(cached\)\' : \s*\'<span class="unavailable">&lt;unavailable&gt;</span>\'\);'
    assert re.search(wind_speed_js_pattern, response.text, re.DOTALL) is not None
    
    # For wind gust
    wind_gust_js_pattern = r'const windGust = data\.weather\.wind_gust !== null && data\.weather\.wind_gust !== undefined \? \s*Math\.round\(data\.weather\.wind_gust\) \+ \' mph\' : \s*\(isCachedWindGust \? Math\.round\(data\.weather\.wind_gust\) \+ \' mph \(cached\)\' : \s*\'<span class="unavailable">&lt;unavailable&gt;</span>\'\);'
    assert re.search(wind_gust_js_pattern, response.text, re.DOTALL) is not None
    
    # For soil moisture
    soil_moisture_js_pattern = r'const soilMoisture = data\.weather\.soil_moisture_15cm \? Math\.round\(data\.weather\.soil_moisture_15cm\) \+ \'%\' : \s*\(isCachedSoilMoisture \? Math\.round\(data\.weather\.soil_moisture_15cm\) \+ \'% \(cached\)\' : \s*\'<span class="unavailable">&lt;unavailable&gt;</span>\'\);'
    assert re.search(soil_moisture_js_pattern, response.text, re.DOTALL) is not None

@pytest.mark.asyncio
async def test_fire_risk_endpoint_with_cached_data(client, reset_cache, mock_failed_synoptic_api, mock_failed_wunderground_api, populate_cache_with_valid_data):
    """Test that the /fire-risk endpoint returns cached data when APIs fail."""
    # First, populate the cache with valid data
    original_data = populate_cache_with_valid_data
    
    # Now simulate a complete API failure
    background_tasks = MagicMock()
    await refresh_data_cache(background_tasks, force=True)
    
    # Make a request to the API
    response = client.get("/fire-risk")
    
    # Check that the response is successful
    assert response.status_code == 200
    
    # Parse the response
    data = response.json()
    
    # Check that the response includes cache information
    assert "cache_info" in data
    assert data["cache_info"]["using_cached_data"] is True
    
    # Check that the response includes cached_data information
    assert "cached_data" in data
    assert data["cached_data"]["is_cached"] is True
    
    # Check that the explanation mentions cached data
    assert "NOTICE: Displaying cached data" in data["explanation"]

@pytest.mark.asyncio
async def test_fire_risk_endpoint_with_partial_failure(client, reset_cache, mock_partial_api_failure, populate_cache_with_valid_data):
    """Test that the /fire-risk endpoint returns partial cached data when some API calls fail."""
    # First, populate the cache with valid data
    original_data = populate_cache_with_valid_data
    
    # Now simulate a partial API failure
    background_tasks = MagicMock()
    await refresh_data_cache(background_tasks, force=True)
    
    # Make a request to the API
    response = client.get("/fire-risk")
    
    # Check that the response is successful
    assert response.status_code == 200
    
    # Parse the response
    data = response.json()
    
    # Check that the response includes cache information
    assert "cache_info" in data
    assert data["cache_info"]["using_cached_data"] is True
    
    # Check that the weather data includes cached_fields information
    assert "weather" in data
    assert "cached_fields" in data["weather"]
    
    # Check that the specific fields are marked as using cached data
    assert data["weather"]["cached_fields"]["temperature"] is True
    assert data["weather"]["cached_fields"]["soil_moisture"] is True
    
    # Other fields should not be using cached data
    assert data["weather"]["cached_fields"]["humidity"] is False
    assert data["weather"]["cached_fields"]["wind_speed"] is False

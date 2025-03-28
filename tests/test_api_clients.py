import pytest
from unittest.mock import patch, MagicMock
import requests

from api_clients import get_api_token, get_weather_data, get_wunderground_data

@pytest.mark.asyncio
async def test_get_api_token():
    """Test that get_api_token returns a token when the API call is successful."""
    # Mock the requests.get method to return a successful response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"TOKEN": "test_token"}

    with patch('api_clients.requests.get', return_value=mock_response) as mock_get, \
         patch('api_clients.SYNOPTIC_API_KEY', "test_api_key", create=True):
        token = get_api_token()

        # Check that the token is returned
        assert token == "test_token"

        # Check that requests.get was called with the correct URL
        mock_get.assert_called_once_with("https://api.synopticdata.com/v2/auth?apikey=test_api_key")

@pytest.mark.asyncio
async def test_get_api_token_failure():
    """Test that get_api_token returns None when the API call fails."""
    # Mock the requests.get method to raise an exception
    with patch('api_clients.requests.get', side_effect=requests.exceptions.RequestException("Test error")), \
         patch('api_clients.SYNOPTIC_API_KEY', "test_api_key", create=True):
        token = get_api_token()
        
        # Check that None is returned
        assert token is None

@pytest.mark.asyncio
async def test_get_weather_data():
    """Test that get_weather_data returns data when the API call is successful."""
    # Mock the get_api_token function to return a token
    # Mock the requests.get method to return a successful response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"STATION": [{"STID": "TEST"}]}
    
    with patch('api_clients.get_api_token', return_value="test_token"), \
         patch('api_clients.requests.get', return_value=mock_response) as mock_get:
        data = get_weather_data("TEST")
        
        # Check that the data is returned
        assert data == {"STATION": [{"STID": "TEST"}]}
        
        # Check that requests.get was called with the correct URL
        mock_get.assert_called_once_with("https://api.synopticdata.com/v2/stations/latest?stid=TEST&token=test_token")

@pytest.mark.asyncio
async def test_get_weather_data_failure():
    """Test that get_weather_data returns None when the API call fails."""
    # Mock the get_api_token function to return a token
    # Mock the requests.get method to raise an exception
    with patch('api_clients.get_api_token', return_value="test_token"), \
         patch('api_clients.requests.get', side_effect=requests.exceptions.RequestException("Test error")):
        data = get_weather_data("TEST")
        
        # Check that None is returned
        assert data is None

@pytest.mark.asyncio
async def test_get_weather_data_retry():
    """Test that get_weather_data retries when it receives a 401 error."""
    # Mock the get_api_token function to return a token
    # Mock the requests.get method to return a 401 error on first call, then a successful response
    mock_error_response = MagicMock()
    mock_error_response.status_code = 401
    mock_error_response.json.return_value = {"error": "Unauthorized"}
    
    mock_success_response = MagicMock()
    mock_success_response.status_code = 200
    mock_success_response.json.return_value = {"STATION": [{"STID": "TEST"}]}
    
    with patch('api_clients.get_api_token', return_value="test_token"), \
         patch('api_clients.requests.get', side_effect=[mock_error_response, mock_success_response]) as mock_get:
        data = get_weather_data("TEST")
        
        # Check that the data is returned
        assert data == {"STATION": [{"STID": "TEST"}]}
        
        # Check that requests.get was called twice
        assert mock_get.call_count == 2

@pytest.mark.asyncio
async def test_get_wunderground_data():
    """Test that get_wunderground_data returns data when the API call is successful."""
    # Mock the requests.get method to return a successful response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"observations": [{"imperial": {"windGust": 3.0}}]}
    
    with patch('api_clients.requests.get', return_value=mock_response) as mock_get, \
         patch('api_clients.WUNDERGROUND_API_KEY', "test_api_key", create=True):
        data = get_wunderground_data(["TEST"])
        
        # Check that the data is returned
        assert "TEST" in data
        assert data["TEST"] == {"observations": [{"imperial": {"windGust": 3.0}}]}
        
        # Check that requests.get was called with the correct URL
        mock_get.assert_called_once_with("https://api.weather.com/v2/pws/observations/current?stationId=TEST&format=json&units=e&apiKey=test_api_key")

@pytest.mark.asyncio
async def test_get_wunderground_data_failure():
    """Test that get_wunderground_data returns None when the API call fails."""
    # Mock the requests.get method to raise an exception
    with patch('api_clients.requests.get', side_effect=requests.exceptions.RequestException("Test error")), \
         patch('api_clients.WUNDERGROUND_API_KEY', "test_api_key", create=True):
        data = get_wunderground_data(["TEST"])
        
        # Check that the station's data is None
        assert "TEST" in data
        assert data["TEST"] is None

@pytest.mark.asyncio
async def test_get_wunderground_data_empty_response():
    """Test that get_wunderground_data returns None when the API returns an empty response."""
    # Mock the requests.get method to return a successful response with no observations
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"observations": []}
    
    with patch('api_clients.requests.get', return_value=mock_response), \
         patch('api_clients.WUNDERGROUND_API_KEY', "test_api_key", create=True):
        data = get_wunderground_data(["TEST"])
        
        # Check that the station's data is None
        assert "TEST" in data
        assert data["TEST"] is None

import pytest
import requests
from unittest.mock import patch, MagicMock
from api_clients import get_api_token, get_weather_data, get_wunderground_data, get_synoptic_data

# Mock API responses
mock_token_response = {"TOKEN": "mock_token"}
mock_weather_response = {"STATION": []}
mock_wunderground_response = {"observations": [{"imperial": {"windGust": 10}}]}

@patch('api_clients.requests.get')
def test_get_api_token_success(mock_get):
    """Test successful API token retrieval."""
    mock_get.return_value.json.return_value = mock_token_response
    mock_get.return_value.status_code = 200
    token = get_api_token()
    assert token == "mock_token"


@patch('api_clients.requests.get')
def test_get_api_token_failure(mock_get):
    """Test failed API token retrieval."""
    mock_get.return_value.status_code = 400  # Simulate a bad request
    # Properly mock the json method to return a dict instead of a MagicMock
    mock_get.return_value.json.return_value = {"error": "Bad request"}
    # Configure raise_for_status to raise an exception
    mock_get.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError("400 Error")
    token = get_api_token()
    assert token is None


@patch('api_clients.get_api_token')
@patch('api_clients.requests.get')
def test_get_weather_data_success(mock_get, mock_token):
    """Test successful weather data retrieval."""
    mock_token.return_value = "mock_token"
    mock_get.return_value.json.return_value = mock_weather_response
    mock_get.return_value.status_code = 200
    data = get_weather_data("mock_location")
    assert data == mock_weather_response


@patch('api_clients.get_api_token')
@patch('api_clients.requests.get')
def test_get_weather_data_failure(mock_get, mock_token):
    """Test failed weather data retrieval."""
    mock_token.return_value = "mock_token"
    mock_get.return_value.status_code = 400
    # Also need to properly mock the json method to avoid MagicMock being returned
    mock_get.return_value.json.return_value = {"error": "Bad request"}
    # Configure raise_for_status to raise an exception
    mock_get.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError("400 Error")
    
    data = get_weather_data("mock_location")
    assert data is None


@patch('api_clients.get_api_token')
@patch('api_clients.requests.get')
def test_get_weather_data_retry(mock_get, mock_token):
    """Test weather data retrieval with retry."""
    mock_token.return_value = "mock_token"
    responses = [MagicMock(status_code=401),  # First call fails with 401
                 MagicMock(status_code=200, json=lambda: mock_weather_response)]
    mock_get.side_effect = responses
    data = get_weather_data("mock_location")
    assert data == mock_weather_response


@patch('api_clients.get_api_token')
@patch('api_clients.requests.get')
def test_get_weather_data_max_retries(mock_get, mock_token):
    """Test weather data retrieval exceeding max retries."""
    mock_token.return_value = "mock_token"
    mock_get.return_value.status_code = 401
    data = get_weather_data("mock_location")
    assert data is None


@patch('api_clients.requests.get')
def test_get_wunderground_data_success(mock_get):
    """Test successful wunderground data retrieval."""
    mock_get.return_value.json.return_value = mock_wunderground_response
    mock_get.return_value.status_code = 200
    data = get_wunderground_data(["mock_station"])
    assert data["mock_station"] == mock_wunderground_response


@patch('api_clients.requests.get') # Added patch
def test_get_wunderground_data_missing_key(mock_get):
    """Test wunderground data retrieval with missing key in response."""
    mock_data = {"observations": [{}]} # Missing 'imperial'
    mock_get.return_value.json.return_value = mock_data
    mock_get.return_value.status_code = 200
    
    # The implementation actually returns the data as-is since it only checks if "observations" exists
    # It doesn't check for the "imperial" key specifically
    data = get_wunderground_data(["mock_station"])
    
    # The function should return the data even though it doesn't have the imperial key
    assert data["mock_station"] == mock_data

@patch('api_clients.requests.get')
def test_get_wunderground_data_failure(mock_get):
    """Test failed wunderground data retrieval."""
    mock_get.return_value.status_code = 400
    data = get_wunderground_data(["mock_station"])
    assert data["mock_station"] is None


@patch('api_clients.get_weather_data')
def test_get_synoptic_data(mock_get_weather_data):

    """Test get_synoptic_data function."""
    mock_get_weather_data.return_value = mock_weather_response
    data = get_synoptic_data()
    assert data == mock_weather_response

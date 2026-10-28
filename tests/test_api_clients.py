import json

import pytest
import requests
from unittest.mock import patch, MagicMock

import api_clients
from api_clients import get_api_token, get_weather_data, get_synoptic_data

# Synoptic tokens are 24-64 alphanumeric characters; get_api_token rejects anything else
VALID_TOKEN = "0123456789abcdef0123456789abcdef"

mock_token_response = {"TOKEN": VALID_TOKEN}
mock_weather_response = {"STATION": []}
saved_fallback_response = {"STATION": [{"STID": "SEYC1"}]}


@pytest.fixture(autouse=True)
def isolated_fallback_file(tmp_path, monkeypatch):
    """Keep the fallback data file in a temporary folder and skip retry back-off delays."""
    fallback_path = tmp_path / "synoptic_fallback_data.json"
    monkeypatch.setattr(api_clients, "FALLBACK_DATA_PATH", str(fallback_path))
    monkeypatch.setattr(api_clients.time, "sleep", lambda seconds: None)
    return fallback_path


@pytest.fixture
def saved_fallback(isolated_fallback_file):
    """A fallback file left by an earlier successful API call."""
    isolated_fallback_file.write_text(json.dumps(saved_fallback_response))


@patch('api_clients.requests.get')
def test_get_api_token_success(mock_get):
    """Test successful API token retrieval."""
    mock_get.return_value.json.return_value = mock_token_response
    mock_get.return_value.status_code = 200
    token = get_api_token()
    assert token == VALID_TOKEN


@patch('api_clients.requests.get')
def test_get_api_token_rejects_malformed_token(mock_get):
    """A token that isn't 24-64 alphanumeric characters is treated as no token."""
    mock_get.return_value.json.return_value = {"TOKEN": "not a token!"}
    mock_get.return_value.status_code = 200
    assert get_api_token() is None


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
def test_get_weather_data_success(mock_get, mock_token, isolated_fallback_file):
    """Successful data is returned and saved as fallback for later failures."""
    mock_token.return_value = VALID_TOKEN
    mock_get.return_value.json.return_value = mock_weather_response
    mock_get.return_value.status_code = 200
    data = get_weather_data("mock_location")
    assert data == mock_weather_response
    assert json.loads(isolated_fallback_file.read_text()) == mock_weather_response


def mock_bad_request(mock_get):
    mock_get.return_value.status_code = 400
    mock_get.return_value.json.return_value = {"error": "Bad request"}
    mock_get.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError("400 Error")


@patch('api_clients.get_api_token')
@patch('api_clients.requests.get')
def test_get_weather_data_failure(mock_get, mock_token):
    """A failed request with no saved fallback data returns None."""
    mock_token.return_value = VALID_TOKEN
    mock_bad_request(mock_get)
    data = get_weather_data("mock_location")
    assert data is None


@patch('api_clients.get_api_token')
@patch('api_clients.requests.get')
def test_get_weather_data_failure_uses_fallback(mock_get, mock_token, saved_fallback):
    """A failed request returns the last saved data, marked as fallback."""
    mock_token.return_value = VALID_TOKEN
    mock_bad_request(mock_get)
    data = get_weather_data("mock_location")
    assert data["STATION"] == saved_fallback_response["STATION"]
    assert data["SUMMARY"]["FALLBACK_DATA"] is True


@patch('api_clients.get_api_token')
@patch('api_clients.requests.get')
def test_get_weather_data_retry(mock_get, mock_token):
    """Test weather data retrieval with retry."""
    mock_token.return_value = VALID_TOKEN
    responses = [MagicMock(status_code=401),  # First call fails with 401
                 MagicMock(status_code=200, json=lambda: mock_weather_response)]
    mock_get.side_effect = responses
    data = get_weather_data("mock_location")
    assert data == mock_weather_response
    assert mock_token.call_count == 2  # A fresh token for the retry


@patch('api_clients.get_api_token')
@patch('api_clients.requests.get')
def test_get_weather_data_max_retries(mock_get, mock_token):
    """After repeated 401s, with no saved fallback data, it gives up and returns None."""
    mock_token.return_value = VALID_TOKEN
    mock_get.return_value.status_code = 401
    data = get_weather_data("mock_location", max_retries=4)
    assert data is None
    assert mock_get.call_count == 5  # The first try plus 4 retries


@patch('api_clients.get_api_token')
@patch('api_clients.requests.get')
def test_get_weather_data_max_retries_uses_fallback(mock_get, mock_token, saved_fallback):
    """After repeated 401s, the last saved data is used."""
    mock_token.return_value = VALID_TOKEN
    mock_get.return_value.status_code = 401
    data = get_weather_data("mock_location", max_retries=2)
    assert data["STATION"] == saved_fallback_response["STATION"]
    assert data["SUMMARY"]["FALLBACK_DATA"] is True


@patch('api_clients.get_weather_data')
def test_get_synoptic_data(mock_get_weather_data):

    """Test get_synoptic_data function."""
    mock_get_weather_data.return_value = mock_weather_response
    data = get_synoptic_data()
    assert data == mock_weather_response

import pytest
import os
import sys
import json
from datetime import datetime, timedelta
import pytz
import socket
import threading
import time
import asyncio
import uvicorn
import httpx # Replaced TestClient with httpx
from unittest.mock import patch, MagicMock, AsyncMock

# Add the parent directory to sys.path to import the main module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fire_risk_logic import calculate_fire_risk
from api_clients import get_weather_data

# Add the parent directory to sys.path to import the main module
# Ensure this runs only once or handle potential multiple additions if conftest is loaded multiple times
if os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) not in sys.path:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Import app from main, assuming main.py initializes the FastAPI app instance
# If app is defined directly in endpoints.py, keep the original import
try:
    from main import app
except ImportError:
    from endpoints import app # Fallback if app is directly in endpoints

from cache import data_cache


# --- Removed live_server_url fixture as it seems unused and may cause async conflicts ---


# --- Existing Fixtures ---


@pytest.fixture(scope="function")
async def client():
    """Return an httpx.AsyncClient for the FastAPI app."""
    # Use httpx.AsyncClient for async testing with function scope to match event_loop fixture
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client

@pytest.fixture(scope="function")
async def admin_client(client):
    """The test client with a valid admin session cookie."""
    from admin_endpoints import admin_sessions
    token = "test-admin-session-token"
    admin_sessions[token] = {"ip": "test", "created_at": time.time()}
    client.cookies.set("session_token", token)
    yield client
    admin_sessions.pop(token, None)
    
@pytest.fixture(scope="function")
def event_loop():
    """Create an event loop for each test."""
    # Create a new loop for each test
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    # Close the loop after the test is done
    if not loop.is_closed():
        loop.close()

@pytest.fixture
def reset_cache(): # Reverted fixture to sync
    """Reset the data cache before and after each test."""
    # Store original cache state
    original_cache = {
        "synoptic_data": data_cache.synoptic_data,
        "wunderground_data": data_cache.wunderground_data,
        "fire_risk_data": data_cache.fire_risk_data,
        "last_updated": data_cache.last_updated,
        "last_valid_data": data_cache.last_valid_data.copy(),
        "cached_fields": data_cache.cached_fields.copy(),
        "using_cached_data": data_cache.using_cached_data
    }
    
    # Reset cache for test
    data_cache.synoptic_data = None
    data_cache.wunderground_data = None
    data_cache.fire_risk_data = None
    data_cache.last_updated = None
    data_cache.using_cached_data = False
    for field in data_cache.cached_fields:
        data_cache.cached_fields[field] = False
    
    yield
    
    # Restore original cache state
    data_cache.synoptic_data = original_cache["synoptic_data"]
    data_cache.wunderground_data = original_cache["wunderground_data"]
    data_cache.fire_risk_data = original_cache["fire_risk_data"]
    data_cache.last_updated = original_cache["last_updated"]
    data_cache.last_valid_data = original_cache["last_valid_data"]
    data_cache.cached_fields = original_cache["cached_fields"]
    data_cache.using_cached_data = original_cache["using_cached_data"]

@pytest.fixture # Reverted scope to function
def mock_synoptic_response():
    """Return a mock Synoptic API response."""
    return {
        "STATION": [
            {
                "STID": "SEYC1",
                "OBSERVATIONS": {
                    "air_temp_value_1": {"value": 0.5},
                    "relative_humidity_value_1": {"value": 98.0},
                    "wind_speed_value_1": {"value": 0.0}
                }
            },
            {
                "STID": "C3DLA",
                "OBSERVATIONS": {
                    "soil_moisture_value_1": {"value": 22.0}
                }
            }
        ]
    }

@pytest.fixture # Reverted scope to function
def mock_wunderground_response():
    """Return a mock Weather Underground API response."""
    return {
        "observations": [
            {
                "imperial": {
                    "windGust": 3.0
                }
            }
        ]
    }



@pytest.fixture
def real_cache():
    """A real DataCache, used by cache_refresh, that neither reads nor writes the cache files on disk."""
    from cache import DataCache
    with patch.object(DataCache, "_load_cache_from_disk", return_value=(False, None)), \
         patch.object(DataCache, "_save_cache_to_disk"):
        cache = DataCache()
        cache.max_retries = 1
        cache.retry_delay = 0
        with patch('cache_refresh.data_cache', cache):
            yield cache


# --- Fixture using patch to mock API calls within cache_refresh ---

@pytest.fixture
def mock_api_responses(mock_synoptic_response):
    """Mock API responses by patching the functions called by cache_refresh."""
    # Patch only the Synoptic data function
    with patch('cache_refresh.get_synoptic_data', return_value=mock_synoptic_response):
        yield


# --- Fixtures for specific failure scenarios ---

@pytest.fixture
def mock_failed_synoptic_api():
    """Mock a failed Synoptic API response."""
    with patch('api_clients.get_weather_data', return_value=None):
        yield

@pytest.fixture
def mock_failed_wunderground_api():
    """Mock a failed Weather Underground API response."""
    with patch('tests.mock_utils.get_wunderground_data', return_value=None):
        yield

@pytest.fixture
def mock_partial_api_failure(mock_synoptic_response):
    """Mock a partial API failure where some fields are missing."""
    # Create a copy of the mock response with some fields set to None
    partial_response = mock_synoptic_response.copy()
    partial_response["STATION"][0]["OBSERVATIONS"]["air_temp_value_1"]["value"] = None
    partial_response["STATION"][1]["OBSERVATIONS"]["soil_moisture_value_1"]["value"] = None
    
    with patch('api_clients.get_weather_data', return_value=partial_response):
        yield

@pytest.fixture
def mock_refresh_data_cache():
    """Mock the refresh_data_cache function for tests that depend on it."""
    with patch('cache_refresh.refresh_data_cache', new_callable=AsyncMock) as mock_func:
        mock_func.return_value = True
        yield mock_func

@pytest.fixture
def mock_get():
    """Mock the requests.get function for tests."""
    with patch('requests.get') as mock_func:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True, "data": {"token": "test_token"}}
        mock_func.return_value = mock_response
        yield mock_func

# Mock implementation of get_wunderground_data for tests
def get_wunderground_data(station_id=None):
    """Mock function for the removed get_wunderground_data API client function."""
    return {
        "observations": [
            {
                "imperial": {
                    "windGust": 3.0
                }
            }
        ]
    }

@pytest.fixture
def live_server_url():
    """Mock live_server_url for e2e tests instead of launching a server."""
    # Start a simple HTTP server in a separate thread for testing
    # This replaces the pytest-fastapi live_server which is causing issues
    port = 8000
    url = f"http://localhost:{port}"
    
    # Return the URL without actually starting a server for now
    # Tests can be updated to work with this mock URL
    yield url

@pytest.fixture
def populate_cache_with_valid_data(mock_synoptic_response, mock_wunderground_response):
    """Populate the cache with valid data."""
    # Create a fire risk data object
    weather_data = {
        "air_temp": 0.5,
        "relative_humidity": 98.0,
        "wind_speed": 0.0,
        "soil_moisture_15cm": 22.0,
        "wind_gust": 3.0,
        "data_sources": {
            "weather_station": "SEYC1",
            "soil_moisture_station": "C3DLA",
            "wind_gust_station": "KCASIERR68"
        },
        "cached_fields": {
            "temperature": False,
            "humidity": False,
            "wind_speed": False,
            "soil_moisture": False,
            "wind_gust": False
        }
    }
    
    risk, explanation = calculate_fire_risk(weather_data)
    fire_risk_data = {"risk": risk, "explanation": explanation, "weather": weather_data}
    
    # Update the cache
    pacific_tz = pytz.timezone('America/Los_Angeles')
    current_time = datetime.now(pacific_tz)
    
    # Modified to match the new update_cache signature (removed wunderground_data parameter)
    data_cache.update_cache(mock_synoptic_response, fire_risk_data)
    
    return fire_risk_data


# --- Real-cache alert test environment ---

class _ControllableDatetimeMeta(type):
    # Real datetimes must still pass isinstance checks (e.g. when cache.py serializes to JSON)
    def __instancecheck__(cls, obj):
        return isinstance(obj, datetime)


class _ControllableDatetime(datetime, metaclass=_ControllableDatetimeMeta):
    """datetime whose now() can be pinned by tests (used in place of cache.datetime)."""
    pinned = None

    @classmethod
    def now(cls, tz=None):
        return cls.pinned if cls.pinned is not None else datetime.now(tz)


class AlertTestEnv:
    """Real DataCache instances backed by a temporary data/ folder, with a settable clock.

    Only the weather API, risk calculation, subscriber list and email sending are faked,
    so the real alert rule, risk-level tracking and disk persistence are exercised.
    """
    RED_EFFECTIVE_VALUES = {"temperature": 90.0, "humidity": 8.0, "wind_speed": 20.0,
                            "wind_gust": 28.0, "soil_moisture": 5.0}
    LIVE_WEATHER = {"air_temp": 32, "relative_humidity": 8, "wind_speed": 9, "wind_gust": 12,
                    "soil_moisture_15cm": 5}

    def set_time(self, when):
        _ControllableDatetime.pinned = when

    def start_server(self):
        """A fresh DataCache, as created when the server (re)starts; it loads saved state from disk."""
        from cache import DataCache
        cache = DataCache()
        cache.max_retries = 1
        cache.retry_delay = 0
        return cache

    async def refresh_with_risk(self, cache, risk):
        """Run a real refresh where the calculated risk is `risk`; returns the email-sending mock."""
        from cache_refresh import refresh_data_cache
        with patch('cache_refresh.data_cache', cache), \
             patch('cache_refresh.get_synoptic_data', return_value={"STATION": []}), \
             patch('cache_refresh.combine_weather_data', side_effect=lambda *a, **k: dict(self.LIVE_WEATHER)), \
             patch('cache_refresh.calculate_fire_risk', return_value=(risk, "test", self.RED_EFFECTIVE_VALUES)), \
             patch('cache_refresh.get_active_subscribers', return_value={"subscribers": ["test@example.com"]}), \
             patch('cache_refresh.send_orange_to_red_alert', return_value="test-message-id") as mock_send:
            assert await refresh_data_cache() is True
        return mock_send


@pytest.fixture
def alert_env(tmp_path, monkeypatch):
    """AlertTestEnv running in an empty temporary folder (DataCache uses ./data/weather_cache.json)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    with patch('cache.datetime', _ControllableDatetime):
        yield AlertTestEnv()
    _ControllableDatetime.pinned = None

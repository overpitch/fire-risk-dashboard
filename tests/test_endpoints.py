import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import BackgroundTasks
# Removed TestClient import
from endpoints import app, fire_risk, home, toggle_test_mode # Assuming app is imported here
from cache import DataCache, data_cache
from datetime import datetime, timezone

# Removed local client = TestClient(app) - will use fixture from conftest.py


@pytest.mark.asyncio
async def test_fire_risk_initial_fetch(client): # Added client fixture
    mock_fire_risk_data = {"risk": "low", "explanation": "test"}
    
    # Use a standalone AsyncMock to ensure it gets awaited
    mock_refresh = AsyncMock()
    mock_refresh.return_value = True
    
    # First set fire_risk_data to None to trigger the initial fetch path
    # Then update it to our mock data after the refresh call
    with patch('endpoints.refresh_data_cache', mock_refresh):
        with patch.object(data_cache, "fire_risk_data", None, create=True):
            # Create a side effect to set fire_risk_data after the call
            async def refresh_side_effect(*args, **kwargs):
                # Update the value
                data_cache.fire_risk_data = mock_fire_risk_data
                return True
            
            mock_refresh.side_effect = refresh_side_effect
            
            # Make the request
            response = await client.get("/fire-risk")
            
            # Verify the response
            assert response.status_code == 200
            data = response.json()
            assert data["risk"] == "low"
            
            # Verify our mock was awaited
            mock_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_fire_risk_stale_data(client):
    # Create our test data
    mock_fire_risk_data = {
        "risk": "low", 
        "explanation": "test",
        "weather": {
            "air_temp": 25,
            "relative_humidity": 50,
            "wind_speed": 10,
            "soil_moisture_15cm": 20,
            "wind_gust": 15
        }
    }
    
    # Mock for refresh_data_cache
    mock_refresh = AsyncMock()
    mock_refresh.return_value = True
    
    # Directly spy on the add_task method
    add_task_called = False
    
    # Create a replacement for add_task that tracks if it was called
    def mock_add_task(self, *args, **kwargs):
        nonlocal add_task_called
        add_task_called = True
        # Check that the first argument is our mock refresh
        if args and args[0] == mock_refresh:
            return None
    
    # Apply all our patches
    with patch('endpoints.refresh_data_cache', mock_refresh):
        # Patch BackgroundTasks.add_task method directly
        with patch.object(BackgroundTasks, 'add_task', mock_add_task):
            # Setup data_cache mocks
            with patch.object(data_cache, "fire_risk_data", mock_fire_risk_data):
                with patch.object(data_cache, "is_stale", return_value=True):
                    with patch.object(data_cache, "is_critically_stale", return_value=False):
                        with patch.object(data_cache, "update_in_progress", False):
                            # Make the request
                            response = await client.get("/fire-risk")
                            
                            # Verify response is correct
                            assert response.status_code == 200
                            
                            # Check for expected data structure
                            result = response.json()
                            assert "cache_info" in result
                            
                            # Verify our add_task was called
                            assert add_task_called, "BackgroundTasks.add_task was not called"


@pytest.mark.asyncio
async def test_fire_risk_cache_data_age_indicators(client):
    """Test that cached data properly includes age indicators"""
    # Use the current time
    now = datetime.now(timezone.utc)
    
    # Create mock data with cache fields structure
    mock_fire_risk_data = {
        "risk": "low",
        "explanation": "test",
        "weather": {
            "air_temp": 25,
            "relative_humidity": 50,
            "wind_speed": 10,
            "soil_moisture_15cm": 20,
            "wind_gust": 15,
            "cached_fields": {
                "temperature": True,
                "humidity": True,
                "wind_speed": True,
                "soil_moisture": True,
                "wind_gust": True
            }
        }
    }
    
    # Create mock cache data
    mock_last_valid_data = {
        "fields": {
            "temperature": {"value": 25, "timestamp": now},
            "humidity": {"value": 50, "timestamp": now},
            "wind_speed": {"value": 10, "timestamp": now},
            "soil_moisture": {"value": 20, "timestamp": now},
            "wind_gust": {"value": 15, "timestamp": now}
        },
        "timestamp": now
    }
    
    # Create mock cached_fields map
    mock_cached_fields = {
        "temperature": True,
        "humidity": True,
        "wind_speed": True,
        "soil_moisture": True,
        "wind_gust": True
    }
    
    # Set up all mocks
    with patch.object(data_cache, "fire_risk_data", mock_fire_risk_data):
        with patch.object(data_cache, "last_valid_data", mock_last_valid_data):
            with patch.object(data_cache, "cached_fields", mock_cached_fields):
                with patch.object(data_cache, "using_cached_data", True):
                    with patch.object(data_cache, "is_stale", return_value=False):
                        with patch.object(data_cache, "ensure_complete_weather_data", return_value=mock_fire_risk_data["weather"]):
                            
                            # Make the request
                            response = await client.get("/fire-risk")
                            
                            # Verify response
                            assert response.status_code == 200
                            result = response.json()
                            
                            # Check cache info
                            assert result["cache_info"]["using_cached_data"] is True
                            
                            # Check cached_data field
                            assert "cached_data" in result
                            assert result["cached_data"]["is_cached"] is True
                            assert "age" in result["cached_data"]
                            
                            # Check weather data has cached_fields with timestamps
                            assert "cached_fields" in result["weather"]
                            assert "timestamp" in result["weather"]["cached_fields"]
                            
                            # Check each field has a timestamp
                            for field in ["temperature", "humidity", "wind_speed", "soil_moisture", "wind_gust"]:
                                assert field in result["weather"]["cached_fields"]
                                assert result["weather"]["cached_fields"][field] is True
                                assert field in result["weather"]["cached_fields"]["timestamp"]
                            
                            # Verify modal content
                            assert "modal_content" in result
                            assert "note" in result["modal_content"]
                            assert "Displaying cached weather data" in result["modal_content"]["note"]


@pytest.mark.asyncio
@patch('endpoints.refresh_data_cache', new_callable=AsyncMock)
async def test_fire_risk_critically_stale_data(mock_refresh_data_cache, client):
    mock_fire_risk_data = {"risk": "low", "explanation": "test"}
    mock_refresh_data_cache.return_value = True
    
    # We need to mock wait_for_update since it's called in this case
    with patch.object(data_cache, "wait_for_update", return_value=True):
        # Create a mock for BackgroundTasks
        mock_background_tasks = MagicMock()
        
        # Mock the endpoints.BackgroundTasks to return our mock
        with patch('endpoints.BackgroundTasks', return_value=mock_background_tasks):
            with patch.object(data_cache, "fire_risk_data", mock_fire_risk_data):
                with patch.object(data_cache, "is_stale", return_value=True):
                    with patch.object(data_cache, "is_critically_stale", return_value=True):
                        response = await client.get("/fire-risk?wait_for_fresh=true")
                        
                        assert response.status_code == 200
                        # In this case, the refresh should be awaited directly
                        mock_refresh_data_cache.assert_awaited_once()


@pytest.mark.asyncio
@patch('endpoints.refresh_data_cache', new_callable=AsyncMock)
async def test_fire_risk_refresh_exception(mock_refresh_data_cache, client):
    # Create a mock that will raise an exception when awaited
    mock_refresh_data_cache.side_effect = Exception("Refresh error")
    
    # Create a mock for BackgroundTasks
    mock_background_tasks = MagicMock()
    
    # Mock the endpoints.BackgroundTasks to return our mock
    with patch('endpoints.BackgroundTasks', return_value=mock_background_tasks):
        # Use a try/except block to catch the exception during the test
        try:
            with patch.object(data_cache, "fire_risk_data", None):  # Simulate no cached data
                response = await client.get("/fire-risk")
                
                # If we get here, the exception wasn't propagated correctly
                assert False, "Expected an exception but none was raised"
        except Exception as e:
            # Verify that the correct exception type was raised
            assert str(e) == "Refresh error"
            
            # The test is successful if we caught the expected exception
            pass


@pytest.mark.asyncio
async def test_fire_risk_refresh_timeout(client):
    mock_fire_risk_data = {"risk": "low", "explanation": "test"}
    
    # Create a mock for BackgroundTasks and refresh_data_cache
    mock_background_tasks = MagicMock()
    mock_refresh = AsyncMock()
    mock_refresh.return_value = True
    
    # In endpoints.py, logger is imported from config
    with patch('endpoints.BackgroundTasks', return_value=mock_background_tasks):
        with patch('endpoints.refresh_data_cache', mock_refresh):
            with patch.object(data_cache, "fire_risk_data", mock_fire_risk_data):
                with patch.object(data_cache, "is_stale", return_value=True):
                    with patch.object(data_cache, "is_critically_stale", return_value=True):
                        with patch.object(data_cache, "wait_for_update", return_value=False):
                            with patch('config.logger') as mock_logger:  # Changed to correct import path
                                # Mock the global using_cached_data flag (set to False initially)
                                with patch.object(data_cache, "using_cached_data", False):
                                    response = await client.get("/fire-risk?wait_for_fresh=true")
                                    
                                    assert response.status_code == 200
                                    # Test that using_cached_data is set to True in the response
                                    # even though the global flag is False
                                    assert response.json()["cache_info"]["using_cached_data"] is True


@pytest.mark.asyncio # Made test async
async def test_home(client): # Added client fixture
    response = await client.get("/") # Use await and fixture client
    assert response.status_code == 200
    assert "Fire Weather Advisory" in response.text


@pytest.mark.asyncio
@patch('endpoints.refresh_data_cache', new_callable=AsyncMock)
async def test_toggle_test_mode_enable(mock_refresh_data_cache, client): # Added client fixture
    mock_refresh_data_cache.return_value = True
    with patch.object(data_cache, "last_valid_data", {"timestamp": datetime.now(timezone.utc)}):
        response = await client.get("/toggle-test-mode?enable=true") # Use await and fixture client
        assert response.status_code == 200
        assert response.json()["mode"] == "test"
        assert data_cache.using_cached_data is True


@pytest.mark.asyncio
@patch('endpoints.refresh_data_cache', new_callable=AsyncMock)
async def test_toggle_test_mode_disable(mock_refresh_data_cache, client): # Added client fixture
    mock_refresh_data_cache.return_value = True
    response = await client.get("/toggle-test-mode?enable=false") # Use await and fixture client
    assert response.status_code == 200
    assert response.json()["mode"] == "normal"
    assert data_cache.using_cached_data is False
    mock_refresh_data_cache.assert_awaited_once()


@pytest.mark.asyncio
async def test_toggle_test_mode_no_cached_data(client): # Added client fixture
    with patch.object(data_cache, "last_valid_data", {"timestamp": None}):
        response = await client.get("/toggle-test-mode?enable=true") # Use await and fixture client
        assert response.status_code == 400
        assert response.json()["message"] == "No cached data available yet. Please visit the dashboard first to populate the cache."

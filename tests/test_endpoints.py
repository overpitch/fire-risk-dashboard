import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import BackgroundTasks
# Removed TestClient import
from endpoints import app, fire_risk, home, toggle_test_mode # Assuming app is imported here
from cache import DataCache, data_cache
from datetime import datetime, timezone

# Removed local client = TestClient(app) - will use fixture from conftest.py


@pytest.mark.asyncio
@patch('endpoints.refresh_data_cache', new_callable=AsyncMock)
async def test_fire_risk_initial_fetch(mock_refresh_data_cache, client): # Added client fixture
    mock_fire_risk_data = {"risk": "low", "explanation": "test"}
    mock_refresh_data_cache.return_value = True
    with patch.object(data_cache, "fire_risk_data", None):
        with patch.object(data_cache, "update_cache") as mock_update_cache:
            mock_update_cache.return_value = None
            with patch.object(data_cache, "fire_risk_data", mock_fire_risk_data):
                response = await client.get("/fire-risk") # Use await and fixture client
                assert response.status_code == 200
                data = response.json()
                assert data["risk"] == "low"
                mock_refresh_data_cache.assert_awaited_once()


@pytest.mark.asyncio
@patch('endpoints.refresh_data_cache', new_callable=AsyncMock)
async def test_fire_risk_stale_data(mock_refresh_data_cache, client):
    mock_fire_risk_data = {"risk": "low", "explanation": "test"}
    mock_refresh_data_cache.return_value = True
    
    # Create a mock for BackgroundTasks
    mock_background_tasks = MagicMock()
    
    # Mock the endpoints.BackgroundTasks to return our mock
    with patch('endpoints.BackgroundTasks', return_value=mock_background_tasks):
        with patch.object(data_cache, "fire_risk_data", mock_fire_risk_data):
            with patch.object(data_cache, "is_stale", return_value=True):
                with patch.object(data_cache, "is_critically_stale", return_value=False):
                    with patch.object(data_cache, "update_in_progress", False):
                        # Make the request
                        response = await client.get("/fire-risk")
                        
                        assert response.status_code == 200
                        # For asyncio endpoint functions, we don't use assert_not_awaited() because of how
                        # FastAPI handles dependencies. Instead, we verify the background task was added
                        # But it should add the task to background_tasks
                        mock_background_tasks.add_task.assert_called_once()


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
    mock_refresh_data_cache.side_effect = Exception("Refresh error")
    
    # Create a mock for BackgroundTasks
    mock_background_tasks = MagicMock()
    
    # Mock the endpoints.BackgroundTasks to return our mock
    with patch('endpoints.BackgroundTasks', return_value=mock_background_tasks):
        with patch.object(data_cache, "fire_risk_data", None):  # Simulate no cached data
            # This will trigger a refresh which will fail
            response = await client.get("/fire-risk")
            
            assert response.status_code == 503  # Service unavailable
            assert "Weather data service unavailable" in response.json()["detail"]


@pytest.mark.asyncio
async def test_fire_risk_refresh_timeout(client):
    mock_fire_risk_data = {"risk": "low", "explanation": "test"}
    
    # Create a mock for BackgroundTasks and refresh_data_cache
    mock_background_tasks = MagicMock()
    mock_refresh = AsyncMock()
    mock_refresh.return_value = True
    
    with patch('endpoints.BackgroundTasks', return_value=mock_background_tasks):
        with patch('endpoints.refresh_data_cache', mock_refresh):
            with patch.object(data_cache, "fire_risk_data", mock_fire_risk_data):
                with patch.object(data_cache, "is_stale", return_value=True):
                    with patch.object(data_cache, "is_critically_stale", return_value=True):
                        with patch.object(data_cache, "wait_for_update", return_value=False):
                            with patch('cache.logger') as mock_logger:
                                response = await client.get("/fire-risk?wait_for_fresh=true")
                                
                                assert response.status_code == 200
                                # Ensure the warning was logged
                                mock_logger.warning.assert_called_with("Timeout waiting for fresh data returning potentially stale data")


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

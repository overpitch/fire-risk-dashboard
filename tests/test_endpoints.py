import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from endpoints import app, fire_risk, home, toggle_test_mode
from cache import DataCache, data_cache
from datetime import datetime, timezone

client = TestClient(app)


@pytest.mark.asyncio
@patch('endpoints.refresh_data_cache', new_callable=AsyncMock)
async def test_fire_risk_initial_fetch(mock_refresh_data_cache):
    mock_fire_risk_data = {"risk": "low", "explanation": "test"}
    mock_refresh_data_cache.return_value = True
    with patch.object(data_cache, "fire_risk_data", None):
        with patch.object(data_cache, "update_cache") as mock_update_cache:
            mock_update_cache.return_value = None
            with patch.object(data_cache, "fire_risk_data", mock_fire_risk_data):
                response = client.get("/fire-risk")
                assert response.status_code == 200
                data = response.json()
                assert data["risk"] == "low"
                mock_refresh_data_cache.assert_awaited_once()


@pytest.mark.asyncio
@patch('endpoints.refresh_data_cache', new_callable=AsyncMock)
async def test_fire_risk_stale_data(mock_refresh_data_cache):
    mock_fire_risk_data = {"risk": "low", "explanation": "test"}
    mock_refresh_data_cache.return_value = True

    with patch.object(data_cache, "fire_risk_data", mock_fire_risk_data):
        with patch.object(data_cache, "is_stale", return_value=True):
            with patch.object(data_cache, "is_critically_stale", return_value=False):
                with patch.object(data_cache, "update_in_progress", False):
                    response = client.get("/fire-risk")
                    assert response.status_code == 200
                    mock_refresh_data_cache.assert_not_awaited()  # Should not refresh immediately


@pytest.mark.asyncio
@patch('endpoints.refresh_data_cache', new_callable=AsyncMock)
async def test_fire_risk_critically_stale_data(mock_refresh_data_cache):
    mock_fire_risk_data = {"risk": "low", "explanation": "test"}
    mock_refresh_data_cache.return_value = True

    with patch.object(data_cache, "fire_risk_data", mock_fire_risk_data):
        with patch.object(data_cache, "is_stale", return_value=True):
            with patch.object(data_cache, "is_critically_stale", return_value=True):
                response = client.get("/fire-risk?wait_for_fresh=true")
                assert response.status_code == 200
                mock_refresh_data_cache.assert_awaited_once()


async def test_fire_risk_refresh_exception(mock_refresh_data_cache):
    mock_refresh_data_cache.side_effect = Exception("Refresh error")
    with patch.object(data_cache, "fire_risk_data", None):  # Simulate no cached data
        response = client.get("/fire-risk")
        assert response.status_code == 500
        assert response.json()["detail"] == "Error refreshing data: Refresh error"


@pytest.mark.asyncio
async def test_fire_risk_refresh_timeout():
    with patch.object(data_cache, "fire_risk_data", {"risk": "low", "explanation": "test"}):

        with patch.object(data_cache, "is_stale", return_value=True):
            with patch.object(data_cache, "is_critically_stale", return_value=True):
                with patch.object(data_cache, "wait_for_update", return_value=False):
                    with patch('cache.logger') as mock_logger:
                        response = client.get("/fire-risk?wait_for_fresh=true")
                        assert response.status_code == 200
                        mock_logger.warning.assert_called_with("Timeout waiting for fresh data, returning potentially stale data")


def test_home():
    response = client.get("/")
    assert response.status_code == 200
    assert "Fire Weather Advisory" in response.text


@pytest.mark.asyncio
@patch('endpoints.refresh_data_cache', new_callable=AsyncMock)
async def test_toggle_test_mode_enable(mock_refresh_data_cache):
    mock_refresh_data_cache.return_value = True
    with patch.object(data_cache, "last_valid_data", {"timestamp": datetime.now(timezone.utc)}):
        response = client.get("/toggle-test-mode?enable=true")
        assert response.status_code == 200
        assert response.json()["mode"] == "test"
        assert data_cache.using_cached_data is True


@pytest.mark.asyncio
@patch('endpoints.refresh_data_cache', new_callable=AsyncMock)
async def test_toggle_test_mode_disable(mock_refresh_data_cache):
    mock_refresh_data_cache.return_value = True
    response = client.get("/toggle-test-mode?enable=false")
    assert response.status_code == 200
    assert response.json()["mode"] == "normal"
    assert data_cache.using_cached_data is False
    mock_refresh_data_cache.assert_awaited_once()


@pytest.mark.asyncio
async def test_toggle_test_mode_no_cached_data():
    with patch.object(data_cache, "last_valid_data", {"timestamp": None}):
        response = client.get("/toggle-test-mode?enable=true")
        assert response.status_code == 400
        assert response.json()["message"] == "No cached data available yet. Please visit the dashboard first to populate the cache."

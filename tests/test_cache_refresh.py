import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta, timezone
from cache_refresh import refresh_data_cache, schedule_next_refresh
from cache import DataCache
from api_clients import get_synoptic_data, get_wunderground_data
from data_processing import combine_weather_data
from fire_risk_logic import calculate_fire_risk


@pytest.fixture
def mock_data():
    mock_weather_data = {"STATION": []}
    mock_wunderground_data = {"observations": []}
    mock_combined_data = {"air_temp": 25, "relative_humidity": 50, "wind_speed": 10, "soil_moisture_15cm": 20, "wind_gust": 15}
    mock_fire_risk = "low", "explanation"
    return mock_weather_data, mock_wunderground_data, mock_combined_data, mock_fire_risk


@pytest.mark.asyncio
@patch('cache_refresh.get_synoptic_data')
@patch('cache_refresh.get_wunderground_data')
@patch('cache_refresh.combine_weather_data')
@patch('cache_refresh.calculate_fire_risk')
async def test_refresh_data_cache_success(mock_calculate_fire_risk, mock_combine_weather_data, mock_get_wunderground_data, mock_get_synoptic_data, mock_data, event_loop):
    mock_weather_data, mock_wunderground_data, mock_combined_data, mock_fire_risk = mock_data

    mock_get_synoptic_data.return_value = mock_weather_data
    mock_get_wunderground_data.return_value = mock_wunderground_data
    mock_combine_weather_data.return_value = mock_combined_data
    mock_calculate_fire_risk.return_value = mock_fire_risk

    cache = DataCache()
    assert await refresh_data_cache() is True
    assert cache.fire_risk_data["risk"] == "low"
    assert cache.last_update_success is True


@pytest.mark.asyncio
@patch('cache_refresh.get_synoptic_data')
@patch('cache_refresh.get_wunderground_data')
async def test_refresh_data_cache_api_failure(mock_get_wunderground_data, mock_get_synoptic_data, event_loop):
    mock_get_synoptic_data.return_value = None  # Simulate API failure
    mock_get_wunderground_data.return_value = None

    cache = DataCache()
    with patch('cache.logger') as mock_logger:  # Mock the logger to check for warnings
        assert await refresh_data_cache() is False
        mock_logger.warning.assert_called_with("All critical data fields are missing")

    assert cache.last_update_success is False


@pytest.mark.asyncio
@patch('cache_refresh.get_synoptic_data')
@patch('cache_refresh.get_wunderground_data')
@patch('cache_refresh.asyncio.sleep', new_callable=AsyncMock)  # Mock asyncio.sleep
async def test_refresh_data_cache_retry(mock_sleep, mock_get_wunderground_data, mock_get_synoptic_data, mock_data, event_loop):
    mock_weather_data, mock_wunderground_data, mock_combined_data, mock_fire_risk = mock_data

    mock_get_synoptic_data.side_effect = [None, mock_weather_data]  # Simulate API failure then success
    mock_get_wunderground_data.side_effect = [None, mock_wunderground_data]
    with patch('cache_refresh.combine_weather_data') as mock_combine:
        with patch('cache_refresh.calculate_fire_risk') as mock_calc:
            mock_combine.return_value = mock_combined_data
            mock_calc.return_value = mock_fire_risk
            cache = DataCache()
            assert await refresh_data_cache() is True
            assert cache.fire_risk_data["risk"] == "low"
            mock_sleep.assert_awaited_once()  # Check if asyncio.sleep was called


@pytest.mark.asyncio
@patch('cache_refresh.get_synoptic_data')
@patch('cache_refresh.get_wunderground_data')
@patch('cache_refresh.asyncio.sleep', new_callable=AsyncMock)
async def test_refresh_data_cache_timeout(mock_sleep, mock_get_wunderground_data, mock_get_synoptic_data, event_loop):
    mock_get_synoptic_data.side_effect = asyncio.sleep(0.1)  # Simulate a long API call
    mock_get_wunderground_data.side_effect = asyncio.sleep(0.1)

    cache = DataCache()
    cache.update_timeout = 0.01  # Set a very short timeout
    assert await refresh_data_cache() is False
    mock_sleep.assert_not_awaited()  # asyncio.sleep in refresh_data_cache should not be called


@pytest.mark.asyncio
@patch('cache_refresh.get_synoptic_data')
@patch('cache_refresh.get_wunderground_data')
async def test_refresh_data_cache_cached_data(mock_get_wunderground_data, mock_get_synoptic_data, mock_data, event_loop):
    mock_weather_data, mock_wunderground_data, mock_combined_data, mock_fire_risk = mock_data

    mock_get_synoptic_data.return_value = None
    mock_get_wunderground_data.return_value = None

    cache = DataCache()
    # Populate cache with initial data
    now = datetime.now(timezone.utc)
    past = now - timedelta(minutes=20)
    cache.last_valid_data = {
        "fields": {
            "temperature": {"value": 26, "timestamp": past},
            "humidity": {"value": 11, "timestamp": past},
            "wind_speed": {"value": 21, "timestamp": past},
            "soil_moisture": {"value": 1, "timestamp": past},
            "wind_gust": {"value": 16, "timestamp": past, "stations": {}}
        },
        "synoptic_data": mock_weather_data,
        "wunderground_data": mock_wunderground_data,
        "fire_risk_data": {"risk": "moderate"},
        "timestamp": past
    }

    assert await refresh_data_cache() is True
    assert cache.fire_risk_data["risk"] == "moderate"
    assert cache.using_cached_data is True
    assert cache.cached_fields["temperature"] is True
    assert cache.cached_fields["humidity"] is True
    assert cache.cached_fields["wind_speed"] is True
    assert cache.cached_fields["soil_moisture"] is True
    assert cache.cached_fields["wind_gust"] is True


async def test_schedule_next_refresh_exception(mock_refresh_data_cache, event_loop, caplog):
    mock_refresh_data_cache.side_effect = Exception("Test Exception")
    cache = DataCache()

    await schedule_next_refresh(0.01)

    assert "Error during background refresh: Test Exception" in caplog.text
    assert cache.refresh_task_active is False


@pytest.mark.asyncio
@patch('cache_refresh.refresh_data_cache')
async def test_schedule_next_refresh(mock_refresh_data_cache, event_loop):
    mock_refresh_data_cache.return_value = True

    cache = DataCache()
    with patch('cache.logger') as mock_logger:
        await schedule_next_refresh(0.01)  # Schedule refresh after a short delay
        mock_logger.info.assert_called_with("Scheduling next background refresh in 0.01 minutes")
    mock_refresh_data_cache.assert_awaited_once()
    assert cache.refresh_task_active is False

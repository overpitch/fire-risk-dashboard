"""Admin test conditions must never alert subscribers or change what the public sees."""
import copy
import pytest
from unittest.mock import patch

import cache_refresh
from cache import data_cache
from admin_endpoints import admin_sessions

RED_EFFECTIVE_VALUES = {"temperature": 95.0, "humidity": 5.0, "wind_speed": 25.0,
                        "wind_gust": 35.0, "soil_moisture": 2.0}
LIVE_WEATHER = {"air_temp": 15.0, "relative_humidity": 60.0, "wind_speed": 1.0,
                "wind_gust": 2.0, "soil_moisture_15cm": 30.0}


@pytest.fixture
def live_state():
    """Snapshot and restore the shared alert/display state touched by these tests."""
    saved = (data_cache.previous_risk_level, data_cache.risk_level_timestamp,
             data_cache.last_alerted_timestamp, data_cache.fire_risk_data)
    data_cache.previous_risk_level = "Orange"
    yield
    (data_cache.previous_risk_level, data_cache.risk_level_timestamp,
     data_cache.last_alerted_timestamp, data_cache.fire_risk_data) = saved


def run_red_test(session, test_email="admin@example.com"):
    with patch.object(cache_refresh, "calculate_fire_risk",
                      return_value=("Red", "test explanation", RED_EFFECTIVE_VALUES)), \
         patch.object(cache_refresh, "TEST_ALERT_EMAIL", test_email), \
         patch.object(cache_refresh, "send_orange_to_red_alert", return_value="msg-1") as mock_send, \
         patch.object(cache_refresh, "get_active_subscribers") as mock_subscribers:
        cache_refresh.run_admin_test_conditions(session, copy.deepcopy(LIVE_WEATHER), {"temperature": 95.0})
    return mock_send, mock_subscribers


def test_test_alert_goes_only_to_test_address(live_state):
    session = {}
    live_before = (data_cache.previous_risk_level, data_cache.risk_level_timestamp,
                   data_cache.last_alerted_timestamp, data_cache.fire_risk_data)

    mock_send, mock_subscribers = run_red_test(session)

    mock_send.assert_called_once()
    recipients = mock_send.call_args.args[0]
    assert recipients == ["admin@example.com"]
    assert mock_send.call_args.kwargs["subject_prefix"] == "[TEST] "
    mock_subscribers.assert_not_called()
    assert session["test_email_send_outcome"] == "success"
    assert session["test_fire_risk_data"]["risk"] == "Red"

    # Live alert state and the public dashboard data are untouched
    assert (data_cache.previous_risk_level, data_cache.risk_level_timestamp,
            data_cache.last_alerted_timestamp, data_cache.fire_risk_data) == live_before


def test_repeat_red_test_does_not_resend(live_state):
    session = {}
    run_red_test(session)
    mock_send, _ = run_red_test(session)
    mock_send.assert_not_called()
    assert session["test_email_send_outcome"] == "not_triggered_conditions_met"


def test_no_test_address_means_no_email(live_state):
    session = {}
    mock_send, mock_subscribers = run_red_test(session, test_email=None)
    mock_send.assert_not_called()
    mock_subscribers.assert_not_called()
    assert session["test_email_send_outcome"] == "not_triggered_no_recipients"


def test_test_run_does_not_modify_live_weather(live_state):
    live_weather = copy.deepcopy(LIVE_WEATHER)
    session = {}
    with patch.object(cache_refresh, "calculate_fire_risk",
                      return_value=("Red", "x", RED_EFFECTIVE_VALUES)), \
         patch.object(cache_refresh, "TEST_ALERT_EMAIL", None):
        cache_refresh.run_admin_test_conditions(session, live_weather, {"temperature": 95.0})
    assert live_weather == LIVE_WEATHER
    assert session["test_fire_risk_data"]["weather"]["relative_humidity"] == 5.0


@pytest.mark.asyncio
async def test_fire_risk_shows_test_result_only_to_that_admin(client, admin_client, live_state):
    live = {"risk": "Green", "explanation": "live", "weather": copy.deepcopy(LIVE_WEATHER)}
    data_cache.fire_risk_data = live
    session = admin_sessions["test-admin-session-token"]
    session["manual_weather_overrides"] = {"temperature": 95.0}
    session["test_fire_risk_data"] = {"risk": "Red", "explanation": "test", "weather": copy.deepcopy(LIVE_WEATHER)}
    session["test_email_send_outcome"] = "success"

    with patch.object(data_cache, "is_stale", return_value=False):
        admin_response = await admin_client.get("/fire-risk")
        assert admin_response.json()["risk"] == "Red"
        assert admin_response.json()["test_conditions_active"] is True
        assert admin_response.json()["email_send_outcome"] == "success"

        admin_client.cookies.clear()
        public_response = await admin_client.get("/fire-risk")
    assert public_response.json()["risk"] == "Green"
    assert "test_conditions_active" not in public_response.json()

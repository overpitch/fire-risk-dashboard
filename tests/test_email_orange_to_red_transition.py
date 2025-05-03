import unittest
from unittest.mock import patch, MagicMock
import asyncio
import pytest
from datetime import datetime

# Import the modules we need to test
from cache_refresh import refresh_data_cache
from email_service import send_orange_to_red_alert
from subscriber_service import get_active_subscribers
from config import TIMEZONE

class TestOrangeToRedEmailAlert(unittest.TestCase):
    """Test the Orange to Red email alert functionality."""

    @pytest.mark.asyncio
    @patch('cache_refresh.get_active_subscribers')
    @patch('cache_refresh.send_orange_to_red_alert')
    @patch('cache_refresh.calculate_fire_risk')
    @patch('cache_refresh.fetch_all_data')
    @patch('cache_refresh.data_cache')
    async def test_orange_to_red_transition_sends_email(self, mock_data_cache, mock_fetch_data, 
                                                       mock_calculate_risk, mock_send_alert, 
                                                       mock_get_subscribers):
        """Test that an Orange to Red transition triggers an email alert."""
        # Set up mocks
        mock_data_cache.update_in_progress = False
        mock_data_cache.previous_risk_level = "Orange"
        mock_data_cache.cached_fields = {"temperature": False, "humidity": False, "wind_speed": False, "soil_moisture": False}
        mock_data_cache.ensure_complete_weather_data.return_value = {
            "air_temp": 32,
            "relative_humidity": 12,
            "wind_speed": 25,
            "wind_gust": 35,
            "soil_moisture_15cm": 8
        }
        
        # Mock fetch_all_data to return sample weather data
        mock_fetch_data.return_value = {"data": "sample"}
        
        # Mock calculate_fire_risk to return "Red" risk level
        mock_calculate_risk.return_value = ("Red", "High temperature and low humidity")
        
        # Mock get_active_subscribers to return sample subscribers
        mock_get_subscribers.return_value = {"subscribers": ["test@example.com"]}
        
        # Mock send_orange_to_red_alert to return a message ID
        mock_send_alert.return_value = "test-message-id"
        
        # Call the function being tested
        result = await refresh_data_cache()
        
        # Verify the results
        self.assertTrue(result)  # Refresh should be successful
        mock_get_subscribers.assert_called_once()
        mock_send_alert.assert_called_once()
        
        # Verify the correct weather data was passed to send_alert
        alert_args = mock_send_alert.call_args[0]
        self.assertEqual(alert_args[0], ["test@example.com"])
        self.assertIn('temperature', alert_args[1])
        self.assertIn('humidity', alert_args[1])
        self.assertIn('wind_speed', alert_args[1])
        
        # Verify previous_risk_level was updated
        self.assertEqual(mock_data_cache.previous_risk_level, "Red")

    @patch('email_service.send_email')
    @patch('email_service.jinja_env')
    def test_send_orange_to_red_alert(self, mock_jinja_env, mock_send_email):
        """Test the send_orange_to_red_alert function."""
        # Set up mocks
        html_template_mock = MagicMock()
        text_template_mock = MagicMock()
        html_template_mock.render.return_value = "HTML Content"
        text_template_mock.render.return_value = "Text Content"
        mock_jinja_env.get_template.side_effect = [html_template_mock, text_template_mock]
        mock_send_email.return_value = "test-message-id"
        
        # Test data
        recipients = ["test@example.com"]
        weather_data = {
            "temperature": "32°C",
            "humidity": "12%",
            "wind_speed": "25 mph",
            "soil_moisture": "8%"
        }
        
        # Call the function
        result = send_orange_to_red_alert(recipients, weather_data)
        
        # Verify results
        self.assertEqual(result, "test-message-id")
        mock_jinja_env.get_template.assert_any_call('orange_to_red_alert.html')
        mock_jinja_env.get_template.assert_any_call('orange_to_red_alert.txt')
        mock_send_email.assert_called_once()
        send_args = mock_send_email.call_args[0]
        self.assertEqual(send_args[0], "advisory@scfireweather.org")
        self.assertEqual(send_args[1], recipients)
        self.assertEqual(send_args[2], "URGENT: Fire Risk Level Increased to RED")
        self.assertEqual(send_args[3], "Text Content")
        self.assertEqual(send_args[4], "HTML Content")

if __name__ == '__main__':
    unittest.main()

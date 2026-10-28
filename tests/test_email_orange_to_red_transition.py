import unittest
from unittest.mock import patch, MagicMock
import asyncio
import pytest
from datetime import datetime, timedelta

# Import the modules we need to test
from cache_refresh import refresh_data_cache
from email_service import send_orange_to_red_alert
from subscriber_service import get_active_subscribers
from config import TIMEZONE

class TestOrangeToRedEmailAlert(unittest.TestCase):
    """Test the Orange to Red email alert functionality."""

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

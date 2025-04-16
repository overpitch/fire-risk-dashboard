import pytest
import os
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

# Import the function to test AFTER patching os.getenv
# This ensures the module uses the mocked environment variables during import
with patch.dict(os.environ, {
    'AWS_REGION': 'us-east-1',
    'AWS_ACCESS_KEY_ID': 'test_key_id',
    'AWS_SECRET_ACCESS_KEY': 'test_secret_key',
    # Add dummy dashboard URL for tests needing it
    'DASHBOARD_URL': 'http://test-dashboard.local'
}):
    # Import functions and objects needed for testing
    from email_service import send_test_email, send_email, send_orange_to_red_alert, ses_client, jinja_env

# --- Test Data ---
SENDER_TEST = "test_sender@example.com"
RECIPIENT_TEST = "test_recipient@example.com"
SUBJECT_TEST = "Test Subject"
BODY_TEST = "Test Body"
EXPECTED_MESSAGE_ID = "test-message-id-123"

SENDER_ALERT = "advisory@scfireweather.org"
RECIPIENTS_ALERT = ["sub1@example.com", "sub2@example.com"]
SUBJECT_ALERT = "URGENT: Fire Risk Level Increased to RED"
WEATHER_DATA_ALERT = {
    'temperature': '95F',
    'humidity': '15%',
    'wind_speed': '25 mph',
    'wind_gust': '35 mph',
    'soil_moisture': 'Very Low'
}
DASHBOARD_URL_ALERT = os.getenv('DASHBOARD_URL', 'http://test-dashboard.local') # Use env var or default


# --- Fixtures ---
@pytest.fixture(autouse=True)
def mock_ses_client_fixture():
    """Automatically mock the ses_client for all tests in this module."""
    # We need to mock the client *within* the email_service module
    """Automatically mock the ses_client for all tests in this module."""
    # We need to mock the client *within* the email_service module
    with patch('email_service.ses_client', new_callable=MagicMock) as mock_client:
        # Configure default success response for send_email
        mock_client.send_email.return_value = {'MessageId': EXPECTED_MESSAGE_ID}
        yield mock_client

@pytest.fixture
def mock_jinja_env_fixture():
    """Mock the Jinja2 environment and its methods."""
    with patch('email_service.jinja_env', new_callable=MagicMock) as mock_env:
        mock_template = MagicMock()
        mock_template.render.return_value = "Rendered Template Content"
        mock_env.get_template.return_value = mock_template
        yield mock_env

# --- Tests for send_test_email (existing function, adapted) ---
def test_send_test_email_success(mock_ses_client_fixture):
    """Test successful simple test email sending."""
    # Call the function (using the simplified test function)
    message_id = send_test_email(RECIPIENT_TEST)

    # Assertions for the underlying send_email call
    assert message_id == EXPECTED_MESSAGE_ID
    mock_ses_client_fixture.send_email.assert_called_once_with(
        Source=SENDER_ALERT, # send_test_email uses the alert sender now
        Destination={'ToAddresses': [RECIPIENT_TEST]},
        Message={
            'Subject': {'Charset': 'UTF-8', 'Data': 'SES Test Email from Fire Risk Dashboard'},
            'Body': {
                'Text': {
                    'Charset': 'UTF-8',
                    'Data': 'This is a test email sent via AWS SES using boto3 from the Fire Risk Dashboard application.'
                }
                # No HTML body for this simple test
            }
        }
    )

def test_send_email_client_error(mock_ses_client_fixture, capsys):
    """Test handling of ClientError during generic email sending."""
    # Configure the mock client to raise ClientError
    error_response = {'Error': {'Code': 'MessageRejected', 'Message': 'Email address is not verified.'}}
    mock_ses_client_fixture.send_email.side_effect = ClientError(error_response, 'SendEmail')

    # Call the generic send_email function
    message_id = send_email(SENDER_TEST, [RECIPIENT_TEST], SUBJECT_TEST, BODY_TEST)

    # Assertions
    assert message_id is None
    mock_ses_client_fixture.send_email.assert_called_once() # Ensure it was called
    captured = capsys.readouterr()
    # Check the log message from the generic send_email function
    assert "Error sending email via SES: Email address is not verified." in captured.out

def test_send_email_other_exception(mock_ses_client_fixture, capsys):
    """Test handling of unexpected exceptions during generic email sending."""
    # Configure the mock client to raise a generic Exception
    mock_ses_client_fixture.send_email.side_effect = Exception("Something went wrong")

    # Call the generic send_email function
    message_id = send_email(SENDER_TEST, [RECIPIENT_TEST], SUBJECT_TEST, BODY_TEST)

    # Assertions
    assert message_id is None
    mock_ses_client_fixture.send_email.assert_called_once() # Ensure it was called
    captured = capsys.readouterr()
    assert "An unexpected error occurred during email sending: Something went wrong" in captured.out

def test_send_email_no_recipients(mock_ses_client_fixture, capsys):
    """Test calling send_email with an empty recipient list."""
    message_id = send_email(SENDER_TEST, [], SUBJECT_TEST, BODY_TEST)
    assert message_id is None
    mock_ses_client_fixture.send_email.assert_not_called()
    captured = capsys.readouterr()
    assert "Error: No recipients provided." in captured.out


# --- Tests for send_orange_to_red_alert ---

def test_send_orange_to_red_alert_success_with_templates(mock_ses_client_fixture, mock_jinja_env_fixture):
    """Test successful alert sending using Jinja2 templates."""
    # Call the function
    message_id = send_orange_to_red_alert(RECIPIENTS_ALERT, WEATHER_DATA_ALERT)

    # Assertions
    assert message_id == EXPECTED_MESSAGE_ID

    # Check Jinja calls
    mock_jinja_env_fixture.get_template.assert_has_calls([
        patch.call('orange_to_red_alert.html'),
        patch.call('orange_to_red_alert.txt')
    ], any_order=True)
    assert mock_jinja_env_fixture.get_template.call_count == 2

    # Check render calls (assuming render returns "Rendered Template Content")
    render_context = {'weather': WEATHER_DATA_ALERT, 'dashboard_url': DASHBOARD_URL_ALERT}
    mock_jinja_env_fixture.get_template.return_value.render.assert_has_calls([
        patch.call(render_context),
        patch.call(render_context)
    ], any_order=True) # Order depends on which template is fetched first
    assert mock_jinja_env_fixture.get_template.return_value.render.call_count == 2

    # Check SES call
    mock_ses_client_fixture.send_email.assert_called_once_with(
        Source=SENDER_ALERT,
        Destination={'ToAddresses': RECIPIENTS_ALERT},
        Message={
            'Subject': {'Charset': 'UTF-8', 'Data': SUBJECT_ALERT},
            'Body': {
                'Html': {'Charset': 'UTF-8', 'Data': "Rendered Template Content"},
                'Text': {'Charset': 'UTF-8', 'Data': "Rendered Template Content"}
            }
        }
    )

@patch('email_service.jinja_env', None) # Simulate Jinja env not being available
def test_send_orange_to_red_alert_success_fallback_text(mock_ses_client_fixture, capsys):
    """Test successful alert sending using fallback text when Jinja is unavailable."""
    # Call the function
    message_id = send_orange_to_red_alert(RECIPIENTS_ALERT, WEATHER_DATA_ALERT)

    # Assertions
    assert message_id == EXPECTED_MESSAGE_ID

    # Check SES call (should use fallback text)
    mock_ses_client_fixture.send_email.assert_called_once()
    args, kwargs = mock_ses_client_fixture.send_email.call_args
    assert kwargs['Source'] == SENDER_ALERT
    assert kwargs['Destination'] == {'ToAddresses': RECIPIENTS_ALERT}
    assert kwargs['Message']['Subject']['Data'] == SUBJECT_ALERT
    assert 'Html' not in kwargs['Message']['Body'] # Should only have Text
    assert 'Text' in kwargs['Message']['Body']
    # Check if key weather data is in the fallback text
    assert WEATHER_DATA_ALERT['temperature'] in kwargs['Message']['Body']['Text']['Data']
    assert WEATHER_DATA_ALERT['humidity'] in kwargs['Message']['Body']['Text']['Data']
    assert WEATHER_DATA_ALERT['wind_speed'] in kwargs['Message']['Body']['Text']['Data']
    assert "increased to RED" in kwargs['Message']['Body']['Text']['Data']

    # Check log message
    captured = capsys.readouterr()
    assert "Error: Jinja environment not available. Cannot render templates." in captured.out


def test_send_orange_to_red_alert_template_render_error(mock_ses_client_fixture, mock_jinja_env_fixture, capsys):
    """Test handling of errors during template rendering."""
    # Configure mock template to raise error
    mock_jinja_env_fixture.get_template.return_value.render.side_effect = Exception("Jinja boom!")

    # Call the function
    message_id = send_orange_to_red_alert(RECIPIENTS_ALERT, WEATHER_DATA_ALERT)

    # Assertions
    assert message_id is None
    mock_ses_client_fixture.send_email.assert_not_called() # Should not attempt send
    captured = capsys.readouterr()
    assert "Error rendering email templates: Jinja boom!" in captured.out


def test_send_orange_to_red_alert_ses_error(mock_ses_client_fixture, mock_jinja_env_fixture, capsys):
    """Test handling of SES ClientError during alert sending."""
    # Configure SES mock to raise error
    error_response = {'Error': {'Code': 'Throttling', 'Message': 'Maximum sending rate exceeded.'}}
    mock_ses_client_fixture.send_email.side_effect = ClientError(error_response, 'SendEmail')

    # Call the function
    message_id = send_orange_to_red_alert(RECIPIENTS_ALERT, WEATHER_DATA_ALERT)

    # Assertions
    assert message_id is None
    mock_ses_client_fixture.send_email.assert_called_once() # Should attempt send
    captured = capsys.readouterr()
    assert "Error sending email via SES: Maximum sending rate exceeded." in captured.out


def test_send_orange_to_red_alert_no_recipients(mock_ses_client_fixture, mock_jinja_env_fixture, capsys):
    """Test calling alert function with no recipients."""
    message_id = send_orange_to_red_alert([], WEATHER_DATA_ALERT)

    # Assertions
    assert message_id is None
    mock_ses_client_fixture.send_email.assert_not_called() # Should not attempt send
    captured = capsys.readouterr()
    assert "Error: No recipients provided." in captured.out # Error comes from underlying send_email

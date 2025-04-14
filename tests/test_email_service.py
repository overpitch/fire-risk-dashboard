import pytest
import os
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

# Import the function to test AFTER patching os.getenv
# This ensures the module uses the mocked environment variables during import
with patch.dict(os.environ, {
    'AWS_REGION': 'us-east-1',
    'AWS_ACCESS_KEY_ID': 'test_key_id',
    'AWS_SECRET_ACCESS_KEY': 'test_secret_key'
}):
    from email_service import send_test_email, ses_client

# Test data
SENDER = "test_sender@example.com"
RECIPIENT = "test_recipient@example.com"
SUBJECT = "Test Subject"
BODY = "Test Body"
EXPECTED_MESSAGE_ID = "test-message-id-123"

@pytest.fixture(autouse=True)
def mock_ses_client():
    """Automatically mock the ses_client for all tests in this module."""
    # We need to mock the client *within* the email_service module
    with patch('email_service.ses_client', new_callable=MagicMock) as mock_client:
        yield mock_client

def test_send_test_email_success(mock_ses_client):
    """Test successful email sending."""
    # Configure the mock client's send_email method
    mock_ses_client.send_email.return_value = {'MessageId': EXPECTED_MESSAGE_ID}

    # Call the function
    message_id = send_test_email(SENDER, RECIPIENT, SUBJECT, BODY)

    # Assertions
    assert message_id == EXPECTED_MESSAGE_ID
    mock_ses_client.send_email.assert_called_once_with(
        Destination={'ToAddresses': [RECIPIENT]},
        Message={
            'Body': {
                'Text': {
                    'Charset': 'UTF-8',
                    'Data': BODY,
                },
            },
            'Subject': {
                'Charset': 'UTF-8',
                'Data': SUBJECT,
            },
        },
        Source=SENDER,
    )

def test_send_test_email_client_error(mock_ses_client, capsys):
    """Test handling of ClientError during email sending."""
    # Configure the mock client to raise ClientError
    error_response = {'Error': {'Code': 'MessageRejected', 'Message': 'Email address is not verified.'}}
    mock_ses_client.send_email.side_effect = ClientError(error_response, 'SendEmail')

    # Call the function
    message_id = send_test_email(SENDER, RECIPIENT, SUBJECT, BODY)

    # Assertions
    assert message_id is None
    mock_ses_client.send_email.assert_called_once() # Ensure it was called
    captured = capsys.readouterr()
    assert "Error sending email: Email address is not verified." in captured.out

def test_send_test_email_other_exception(mock_ses_client, capsys):
    """Test handling of unexpected exceptions during email sending."""
    # Configure the mock client to raise a generic Exception
    mock_ses_client.send_email.side_effect = Exception("Something went wrong")

    # Call the function
    message_id = send_test_email(SENDER, RECIPIENT, SUBJECT, BODY)

    # Assertions
    assert message_id is None
    mock_ses_client.send_email.assert_called_once() # Ensure it was called
    captured = capsys.readouterr()
    assert "An unexpected error occurred during sending: Something went wrong" in captured.out

# Optional: Test case if SES client failed to initialize (e.g., missing env vars)
# This requires a slightly different setup to mock the client *before* import
# or re-importing the module under different mock conditions.
# For simplicity, the current setup assumes the client initializes correctly
# due to the initial os.getenv patch.

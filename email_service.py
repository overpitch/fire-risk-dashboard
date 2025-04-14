import os
import boto3
from botocore.exceptions import ClientError

# Load credentials and region from environment variables
# Ensure these are set in your .env file locally and in Render's environment variables
AWS_REGION = os.getenv('AWS_REGION')
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')

# Initialize the SES client
# Boto3 will automatically use the environment variables if access_key_id and secret_access_key are None
ses_client = boto3.client(
    'ses',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

# Function to send email using SES
def send_test_email(sender, recipient, subject, body_text):
    """
    Sends a test email using AWS SES.

    Args:
        sender (str): The verified sender email address.
        recipient (str): The recipient email address (must be verified if in sandbox).
        subject (str): The subject line of the email.
        body_text (str): The plain text body of the email.

    Returns:
        str: The message ID if successful, None otherwise.
    """
    CHARSET = "UTF-8"

    if not ses_client:
        print("Error: SES client not initialized.")
        return None

    try:
        response = ses_client.send_email(
            Destination={
                'ToAddresses': [
                    recipient,
                ],
            },
            Message={
                'Body': {
                    'Text': {
                        'Charset': CHARSET,
                        'Data': body_text,
                    },
                    # Optionally add HTML body:
                    # 'Html': {
                    #     'Charset': CHARSET,
                    #     'Data': body_html,
                    # },
                },
                'Subject': {
                    'Charset': CHARSET,
                    'Data': subject,
                },
            },
            Source=sender,
            # If you are using a configuration set, specify it here:
            # ConfigurationSetName=CONFIGURATION_SET,
        )
    except ClientError as e:
        print(f"Error sending email: {e.response['Error']['Message']}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during sending: {e}")
        return None
    else:
        message_id = response.get('MessageId')
        print(f"Email sent! Message ID: {message_id}")
        return message_id

if __name__ == '__main__':
    # Example usage (for direct testing of this module)
    # Replace with your SES-verified sender and recipient emails for testing
    SENDER_EMAIL = "advisory@scfireweather.org"
    RECIPIENT_EMAIL = "info@scfireweather.org" # Replace!

    if not all([AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY]):
        print("Error: AWS credentials or region not found in environment variables.")
        print("Please set AWS_REGION, AWS_ACCESS_KEY_ID, and AWS_SECRET_ACCESS_KEY.")
    elif SENDER_EMAIL == "your-verified-sender@example.com" or RECIPIENT_EMAIL == "your-verified-recipient@example.com":
         print("Error: Please replace placeholder SENDER_EMAIL and RECIPIENT_EMAIL in email_service.py before testing.")
    else:
        print("Attempting to send test email...")
        try:
            message_id = send_test_email(
                sender=SENDER_EMAIL,
                recipient=RECIPIENT_EMAIL,
                subject="SES Test Email from Fire Risk Dashboard",
                body_text="This is a test email sent via AWS SES using boto3 from the Fire Risk Dashboard application."
            )
            if message_id:
                print(f"Test email sent successfully. Message ID: {message_id}")
            else:
                print("Test email sending failed.")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

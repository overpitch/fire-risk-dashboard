import os
import boto3
from botocore.exceptions import ClientError
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Setup Jinja2 environment (assuming templates are in a 'templates' directory)
# We'll create this directory later if needed.
try:
    template_loader = FileSystemLoader(searchpath="./templates")
    jinja_env = Environment(
        loader=template_loader,
        autoescape=select_autoescape(['html', 'xml'])
    )
except Exception as e:
    print(f"Warning: Jinja2 template directory './templates' not found or error initializing: {e}")
    jinja_env = None # Fallback or handle as needed

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

# Function to send a generic email using SES
def send_email(sender, recipients, subject, body_text, body_html=None):
    """
    Sends an email using AWS SES to one or more recipients.

    Args:
        sender (str): The verified sender email address.
        recipients (list): A list of recipient email addresses.
        subject (str): The subject line of the email.
        body_text (str): The plain text body of the email.
        body_html (str, optional): The HTML body of the email. Defaults to None.

    Returns:
        str: The message ID if successful, None otherwise.
    """
    CHARSET = "UTF-8"

    if not ses_client:
        print("Error: SES client not initialized.")
        return None
    if not recipients:
        print("Error: No recipients provided.")
        return None

    message_body = {
        'Text': {
            'Charset': CHARSET,
            'Data': body_text,
        }
    }
    if body_html:
        message_body['Html'] = {
            'Charset': CHARSET,
            'Data': body_html,
        }

    try:
        # Note: send_email sends to all recipients in the list as one API call
        response = ses_client.send_email(
            Source=sender,
            Destination={'ToAddresses': recipients},
            Message={
                'Subject': {'Charset': CHARSET, 'Data': subject},
                'Body': message_body
            }
            # If you are using a configuration set, specify it here:
            # ConfigurationSetName=CONFIGURATION_SET,
        )
    except ClientError as e:
        # More specific error handling can be added here (e.g., for throttling)
        print(f"Error sending email via SES: {e.response['Error']['Message']}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during email sending: {e}")
        return None
    else:
        # Log success
        message_id = response.get('MessageId')
        print(f"Email sent successfully to {len(recipients)} recipients. Message ID: {message_id}")
        return message_id

# --- Specific Alert Functions ---

def send_orange_to_red_alert(recipients, weather_data):
    """
    Sends the specific 'Orange to Red' fire risk alert email.

    Args:
        recipients (list): List of email addresses to send the alert to.
        weather_data (dict): Dictionary containing current weather parameters
                             (e.g., temp, humidity, wind_speed, soil_moisture).
    """
    sender = "advisory@scfireweather.org" # Use the designated alert sender
    subject = "URGENT: Fire Risk Level Increased to RED"

    if not jinja_env:
        print("Error: Jinja environment not available. Cannot render templates.")
        # Fallback to basic text if templates fail
        body_text = f"""
        Attention: The fire risk level for Sierra City has increased to RED.

        Current Conditions contributing to this level:
        - Temperature: {weather_data.get('temperature', 'N/A')}
        - Humidity: {weather_data.get('humidity', 'N/A')}
        - Wind Speed: {weather_data.get('wind_speed', 'N/A')}
        - Soil Moisture: {weather_data.get('soil_moisture', 'N/A')}

        Please consult the Fire Risk Dashboard for detailed information and safety recommendations: [Link to Dashboard]

        Stay safe,
        Sierra City Fire Weather Advisory
        """
        body_html = None # Or generate basic HTML fallback
    else:
        try:
            # Render templates (assuming template files exist)
            # TODO: Create 'orange_to_red_alert.html' and 'orange_to_red_alert.txt' in ./templates/
            html_template = jinja_env.get_template('orange_to_red_alert.html')
            text_template = jinja_env.get_template('orange_to_red_alert.txt')
            dashboard_url = "https://scfireweather.org/dashboard.html"
            body_html = html_template.render(weather=weather_data, dashboard_url=dashboard_url)
            body_text = text_template.render(weather=weather_data, dashboard_url=dashboard_url)
        except Exception as e:
            print(f"Error rendering email templates: {e}")
            # Consider fallback mechanism here as well
            return None # Or raise error

    # Send the email using the generic function
    return send_email(sender, recipients, subject, body_text, body_html)


# --- Test Functions (Optional) ---

def send_test_email(recipient):
    """Sends a simple test email to a single recipient."""
    sender = "advisory@scfireweather.org" # Or a different test sender
    subject = "SES Test Email from Fire Risk Dashboard"
    body_text = "This is a test email sent via AWS SES using boto3 from the Fire Risk Dashboard application."
    print(f"Attempting to send test email to {recipient}...")
    return send_email(sender, [recipient], subject, body_text)


def send_test_orange_to_red_alert(recipient_email):
    """
    Sends a test Orange to Red alert email to a specified recipient.
    This is useful for testing the email templates and AWS SES connectivity.

    Args:
        recipient_email (str): The email address to send the test alert to.

    Returns:
        str: The message ID if successful, None otherwise.
    """
    # Sample weather data for testing
    test_weather_data = {
        'temperature': '32°C (90°F)',
        'humidity': '12%',
        'wind_speed': '25 mph',
        'wind_gust': '35 mph',
        'soil_moisture': '8%'
    }

    print(f"Sending test Orange to Red alert email to {recipient_email}...")
    return send_orange_to_red_alert([recipient_email], test_weather_data)


if __name__ == '__main__':
    # Example usage for direct testing
    TEST_RECIPIENT = "overpitch@icloud.com"  # Default test recipient

    if not all([AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY]):
        print("Error: AWS credentials or region not found in environment variables.")
    else:
        # Test the orange_to_red_alert with templates
        print("\nAttempting to send Orange-to-Red alert with templates...")
        test_weather_data = {
            'temperature': '32°C (90°F)',
            'humidity': '12%',
            'wind_speed': '25 mph',
            'wind_gust': '35 mph',
            'soil_moisture': '8%'
        }
        
        send_orange_to_red_alert([TEST_RECIPIENT], test_weather_data)

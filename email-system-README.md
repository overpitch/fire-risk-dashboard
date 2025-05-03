# Fire Risk Dashboard Email System

This document provides an overview of the email alert system for the Sierra City Fire Risk Dashboard.

## System Overview

The email system is designed to automatically send alerts to subscribers when the fire risk level transitions from Orange to Red. 

### Components

1. **Email Service (`email_service.py`)**
   - Handles email sending via AWS SES
   - Provides template rendering
   - Contains utility functions for sending both test and real alerts

2. **Subscriber Management (`subscriber_service.py`)**
   - Manages a SQLite database of subscribers
   - Provides functions for adding, removing, and fetching subscribers
   - Supports bulk import of subscribers

3. **Risk Level Monitoring (`cache_refresh.py`)**
   - Detects transitions in risk level
   - Triggers email alerts when risk level changes from Orange to Red
   - Formats weather data for inclusion in emails

4. **Email Templates**
   - HTML template: `templates/orange_to_red_alert.html`
   - Text template: `templates/orange_to_red_alert.txt`
   - Both templates include current weather data and dashboard link

## Testing

To test the email system:

```bash
# Activate the virtual environment
. venv/bin/activate

# Send a test email to the default recipient (overpitch@icloud.com)
python test_email_send.py

# Send a test email to a different recipient
python test_email_send.py recipient@example.com
```

## AWS SES Configuration

The system uses AWS SES for email delivery. Required environment variables:

- `AWS_REGION` - AWS region where SES is configured
- `AWS_ACCESS_KEY_ID` - Access key for AWS
- `AWS_SECRET_ACCESS_KEY` - Secret key for AWS

Note: The system is currently in AWS SES sandbox mode, meaning emails can only be sent to verified recipients. Production access needs to be requested from AWS to send to all subscribers.

## Email Content

The Orange to Red alert emails contain:
- Alert header indicating risk level increase
- Current weather conditions (temperature, humidity, wind speed, soil moisture)
- Link to the dashboard for more information
- Unsubscribe instructions (via email to info@scfireweather.org)

## Future Improvements

1. Move out of AWS SES sandbox mode to enable sending to all subscribers
2. Add additional email types (e.g., daily status reports)
3. Implement better error handling and retries for email sending
4. Add dashboard screenshot attachments in emails

#!/usr/bin/env python
"""
Test script for sending Orange to Red alert emails.
This script can be run directly to test the email functionality.
"""
import os
import sys
from email_service import send_test_orange_to_red_alert, send_orange_to_red_alert

def main():
    print("Fire Risk Dashboard - Email Testing Tool")
    print("----------------------------------------")
    
    # Check if AWS credentials are set
    if not all([os.getenv('AWS_REGION'), os.getenv('AWS_ACCESS_KEY_ID'), os.getenv('AWS_SECRET_ACCESS_KEY')]):
        print("Error: AWS credentials are not set in environment variables.")
        print("Please set AWS_REGION, AWS_ACCESS_KEY_ID, and AWS_SECRET_ACCESS_KEY.")
        return 1
    
    # Default recipient
    default_recipient = "overpitch@icloud.com"
    
    # Allow command-line override of recipient
    if len(sys.argv) > 1:
        recipient = sys.argv[1]
    else:
        recipient = default_recipient
    
    print(f"Sending test email to: {recipient}")
    
    # Test weather data
    test_data = {
        'temperature': '32°C (90°F)',
        'humidity': '12%',
        'wind_speed': '25 mph',
        'wind_gust': '35 mph',
        'soil_moisture': '8%'
    }
    
    # Send the test email
    message_id = send_orange_to_red_alert([recipient], test_data)
    
    if message_id:
        print(f"Success! Email sent with Message ID: {message_id}")
        return 0
    else:
        print("Failed to send email. Check the logs for more information.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

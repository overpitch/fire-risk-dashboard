# AWS SES Integration Roadmap for Fire Risk Dashboard

This document outlines the plan for integrating AWS Simple Email Service (SES) with the Sierra City Fire Risk Dashboard to enable both event-triggered alerts and scheduled report distribution based on real-time weather data and fire risk assessments.

---

## 1. AWS SES Account Setup and Configuration

- **Create/Access AWS Account:** [ASSUMED COMPLETE]
  - Sign up or log in to your AWS account.
  - Create IAM users with appropriate SES permissions. [COMPLETED - Dedicated user `fire-risk-dashboard-ses-user` created]
  
- **SES Configuration:**
  - Verify sender/recipient email addresses (`advisory@scfireweather.org`, `info@scfireweather.org`). [COMPLETED]
  - Verify your domain (`scfireweather.org`) for improved deliverability and professional appearance. [COMPLETED - Per user confirmation]
  - Request production access to move out of the SES sandbox environment. [PENDING]

- **Email Authentication Setup:**
  - Configure DKIM, SPF, and DMARC records for your domain. [COMPLETED - Per user confirmation via Cloudflare CNAMEs/TXT]
  - Create dedicated sending identities for different notification types (alerts vs. reports). [COMPLETED - `advisory@scfireweather.org` verified for alerts]

- **Credentials Management:**
  - Store AWS credentials securely using environment variables on Render. [COMPLETED - Added to Render and local .env]
  - Implement credential rotation practices following AWS best practices. [PENDING]

---

## 2. Notification Types and Content Design

- **Risk-Level Change Alerts (Orange -> Red Only):**
  - **Trigger Condition:** Emails will *only* be sent when the calculated fire risk level transitions from **Orange** to **Red**. No alerts will be sent for other transitions (e.g., Red -> Orange, or transitions involving other potential levels if they existed).
  - **Content:** Design an email template specifically for the Orange-to-Red alert.
  - **Key Information:** Include the current weather parameters (temperature, humidity, wind speed, soil moisture) that contributed to the Red status.
  - **Clarity:** Clearly state that the risk level has increased to Red and advise recipients to consult the full dashboard for details and safety recommendations.

- **Daily Risk Summary Reports:**
  - Create a template showing 24-hour trends of temperature, humidity, wind speed, and soil moisture.
  - Include screenshot of the current dashboard status.
  
- **System Status Notifications:**
  - Design templates for technical notifications (API failures, extended cache usage, etc.).
  - Target these emails to system administrators rather than general subscribers.

- **Template Development:**
  - Use responsive HTML templates with fallback plain text versions. [COMPLETED - Initial templates `orange_to_red_alert.html` and `.txt` created]
  - Incorporate your existing fire risk color coding and branding. [COMPLETED - Basic red theme used in HTML template]
  - Design templates to display properly on mobile devices. [IN PROGRESS - Basic responsive styles included, needs wider testing]

---

## 3. Integration with Fire Risk Dashboard Backend

- **Event-Based Triggers:**
  - Modify `fire_risk_logic.py` to detect meaningful changes in risk levels. [PENDING - Logic currently resides entirely in `cache_refresh.py`]
  - Create hooks in `cache_refresh.py` to trigger emails when data is significantly updated. [COMPLETED - Orange-to-Red transition hook implemented]
  - Implement logic to prevent notification flooding during rapidly changing conditions. [PENDING]

- **Dashboard Screenshot Automation:**
  - Implement headless browser automation (Selenium or Puppeteer) to capture dashboard state.
  - Store screenshots temporarily in memory or S3 before email attachment.
  - Include timestamps and condition indicators in the screenshot.

- **Cache-Aware Notifications:**
  - Include data freshness indicators in emails when using cached data.
  - Add special notifications for extended periods of cached-only operation.

- **Email Sending Module:**
  - Create a new module `email_service.py` to handle all SES interactions. [COMPLETED]
  - Implement boto3-based functions for sending different types of emails. [COMPLETED - Generic `send_email` and specific `send_orange_to_red_alert` implemented]
  - Add robust error handling and retry logic. [IN PROGRESS - Basic ClientError handling in `send_email`, needs refinement for retries/throttling]
  - Integrate Jinja2 for HTML/Text templating. [COMPLETED]

---

## 4. Subscriber Management System

- **Database Schema:**
  - Design a schema for storing subscriber information (email, name, preferences). [COMPLETED - Basic SQLite schema in `subscriber_service.py`]
  - Include subscription status, preference settings, and audit fields. [COMPLETED - `is_subscribed`, `created_at`, `unsubscribed_at` included]
  - Consider using DynamoDB or similar AWS service for tight integration. [PENDING - Currently using SQLite]

- **Subscriber Management:**
  - Implement function to retrieve active subscribers. [COMPLETED - `get_active_subscribers` in `subscriber_service.py`]
  - Implement bulk import from CSV/XLSX files. [COMPLETED - `bulk_import_subscribers` in `subscriber_service.py`]
  - Implement file processing logic for extracting emails. [COMPLETED - `file_processor.py`]

- **Subscription Management UI:**
  - Create simple web forms for subscription sign-up and management.
  - Implement preference controls (alert types, frequency, thresholds).
  - Design mobile-friendly interfaces for community access.
  - Add file upload for subscriber lists. [COMPLETED - In admin.html UI]

- **API Endpoints:**
  - Add new endpoints in `endpoints.py` for subscription management. [PENDING]
  - Implement secure token-based unsubscribe links. [PENDING - Placeholder in templates]
  - Create admin endpoints for subscription list management. [COMPLETED - `/admin/import-subscribers` in `admin_endpoints.py`]

- **Compliance Features:**
  - Implement double opt-in flows with confirmation emails.
  - Add unsubscribe links to all emails and honor opt-out requests immediately.
  - Store consent records and timestamps.

---

## 5. Scheduling and Automation

- **Scheduled Reports:**
  - Configure daily report generation at 09:00 Pacific time.
  - Implement weekly summary options showing 7-day trends.

- **Conditional Triggers:**
  - Set up logic to trigger emails only when specific thresholds are crossed.
  - Allow subscribers to set their own notification thresholds.

- **Rate Limiting and Throttling:**
  - Implement controls to prevent excessive notifications during rapidly changing conditions.
  - Add cool-down periods between successive alerts of the same type.

- **Implementation Options:**
  - Use Render's scheduled jobs for time-based emails.
  - Implement internal scheduling for event-based notifications.
  - Consider AWS EventBridge for more complex scheduling needs.

---

## 6. Testing Strategy

- **Admin UI Email Testing Functionality:** [PENDING]
  - Add a dedicated section in the Admin UI for testing email alerts.
  - Implement controls to simulate Orange-to-Red transitions without affecting the public dashboard.
  - Create an interface to send test emails to verified subscribers.
  - Add a log of test email activity for monitoring and debugging.

- **Email Template Testing:**
  - Test templates across major email clients (Gmail, Outlook, Apple Mail).
  - Verify mobile display of all templates.
  - Test with actual fire risk data from production or realistic test data.

- **Deliverability Testing:**
  - Use SES simulator addresses to test delivery without sending real emails.
  - Monitor initial sending reputation metrics closely.

- **Load Testing:**
  - Simulate high-volume sending scenarios to ensure system stability.
  - Test subscriber database performance with realistic data volumes.

- **End-to-End Testing:**
  - Create automated tests covering the complete notification workflow. [COMPLETED - Basic test for Orange-to-Red transition implemented]
  - Test all subscription management functions.

---

## 7. Monitoring and Maintenance

- **SES Performance Metrics:**
  - Track delivery rates, opens, clicks, bounces, and complaints.
  - Set up CloudWatch alarms for bounce rate thresholds.

- **Logging System:**
  - Implement detailed logging for all email operations.
  - Record notification triggers, delivery attempts, and subscriber actions.

- **Reputation Management:**
  - Automatically remove bouncing addresses from your list.
  - Process and honor complaint feedback loops.
  - Regularly clean your subscriber list of inactive addresses.

- **Regular Audits:**
  - Schedule quarterly reviews of email performance.
  - Test all notification pathways during audits.

---

## 8. Security Considerations

- **Data Protection:**
  - Encrypt subscriber data at rest and in transit.
  - Implement appropriate access controls for subscriber information.
  - Consider GDPR and CCPA compliance requirements.

- **SES-Specific Security:**
  - Review AWS security best practices for SES.
  - Implement sending restrictions to prevent unauthorized use.
  - Consider dedicated IAM roles with minimum necessary permissions.

- **Secure Link Generation:**
  - Use signed URLs for unsubscribe and preference management links.
  - Implement expiration for security-sensitive links.

---

## 9. Deployment Plan

- **Phased Rollout:**
  - Begin with system administrator notifications only.
  - Gradually add official community stakeholders.
  - Finally open to public subscription.

- **Initial Deployment:**
  - Deploy with limited alert types to test system stability.
  - Monitor closely for any performance impacts on the main dashboard.

- **Production Monitoring:**
  - Implement enhanced logging during initial deployment.
  - Create a dashboard for email operation statistics.

---

## 10. Future Enhancements

- **SMS Integration:**
  - Consider adding text message alerts for critical conditions using AWS SNS.

- **Dynamic Content:**
  - Implement personalized content based on subscriber location or preferences.

- **API Extensions:**
  - Consider offering an API for third-party applications to access alert data.

- **Multi-channel Notification:**
  - Explore integration with other notification channels (mobile push, webhooks, etc.).

---

This enhanced roadmap provides a comprehensive guide for integrating AWS SES with the Sierra City Fire Risk Dashboard, ensuring reliable delivery of critical fire risk information to community stakeholders and residents.

---

## 8. Subscriber Management System

While AWS SES handles the email delivery, managing your subscriber list is your application's responsibility. This section outlines how to build and manage a subscriber system:

### 1. Database Table

Create a table to store subscriber emails and their status:

```sql
CREATE TABLE subscribers (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  is_subscribed BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT NOW(),
  unsubscribed_at TIMESTAMP
);
```

### 2. Subscription Form

Develop a frontend form where users can submit their email to subscribe. This form should:
- POST to your backend
- Validate the email address
- Add the address to your `subscribers` table

### 3. Unsubscribe Mechanism

Each email should include a unique unsubscribe link. Use a UUID or secure token in the URL that:
- Identifies the subscriber
- Updates their `is_subscribed` status to `false` when clicked

### 4. Email Sending Logic

When sending emails:
- Query only emails with `is_subscribed = TRUE`
- Handle bounces and invalid addresses (optional)

### 5. Optional: Double Opt-In

For anti-spam compliance, consider sending a confirmation email after signup. Only activate subscriptions when the user confirms.

### Technologies

| Component           | Suggested Tools               |
|---------------------|-------------------------------|
| Backend             | Flask / FastAPI               |
| Database            | SQLite, PostgreSQL            |
| Scheduler           | Render Scheduled Jobs         |
| Email Sending       | AWS SES via Boto3             |
| Token Management    | Python `uuid` or secure hash  |
| Templates           | Jinja2 (for email formatting) |

This subscriber system will let you securely manage your daily distro list with support for user consent, easy opt-out, and automated delivery.

---

## 11. API Reliability and Access Management

The system's ability to send accurate alerts depends critically on reliable access to weather data. Recent diagnostics have identified API access issues that must be addressed:

### 1. Synoptic API Access Restoration (URGENT)

- **Issue Identified**: 403 Forbidden errors when requesting station data despite successful authentication
- **Error Message**: "Unauthorized. Review your account access settings in the customer console"
- **Root Causes to Investigate**:
  - API key permissions may be insufficient for the requested stations
  - Account subscription may have expired or been downgraded
  - Station IDs may have changed or are no longer available under current plan

### 2. API Access Management Plan

- **Account Review**:
  - Log in to Synoptic customer console to review subscription status
  - Verify that requested stations (C3DLA, SEYC1, 629PG) are available under current plan
  - Request plan adjustment if necessary to access required stations

- **API Key Management**:
  - Generate new API key with appropriate permissions
  - Securely update API key in environment variables (Render and local development)
  - Implement key rotation schedule to prevent future access issues

- **Error Handling Improvements**:
  - Enhance error messages to clearly indicate when API access issues occur
  - Implement more detailed logging to capture specific API response codes
  - Create admin notification pathway for API subscription/access issues

- **Response Monitoring**:
  - Add regular checks for API response validity beyond HTTP status codes
  - Monitor API quota usage to anticipate potential throttling or limits
  - Create fallback data sources for critical stations when possible

### 3. Implementation Timeline

| Task                                      | Priority | Timeline    |
|-------------------------------------------|----------|-------------|
| Console login and subscription validation | Critical | Immediate   |
| Station access verification               | Critical | Immediate   |
| API key regeneration and update           | Critical | Immediate   |
| Enhanced error monitoring                 | High     | 1-2 days    |
| Admin notification system                 | High     | 2-3 days    |
| Documentation update                      | Medium   | 1 week      |
| Long-term monitoring improvements         | Medium   | 2-4 weeks   |

This section addresses critical reliability concerns that directly impact the core functionality of the Fire Risk Dashboard and consequently the email notification system. Resolving these API access issues must be prioritized before proceeding with further email system enhancements.

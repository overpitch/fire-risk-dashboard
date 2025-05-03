# Admin UI Enhancement for Email Alert Testing

## Background

The Fire Risk Dashboard includes an email alert system that sends notifications to subscribers when the fire risk level transitions from Orange to Red. However, waiting for this transition to occur naturally could take months, making it impractical for testing purposes. To address this, we need to add a feature to the Admin UI that allows administrators to simulate this transition and send test emails to verified subscribers.

## Current Implementation

1. **Email System**: 
   - Successfully implemented in `email_service.py`
   - Templates created in `templates/orange_to_red_alert.html` and `.txt`
   - Subscriber management handled in `subscriber_service.py`
   - Orange-to-Red transition detection in `cache_refresh.py`

2. **Admin UI**:
   - Protected with PIN authentication (1446)
   - Already includes Test/Normal mode toggle
   - Has subscriber management section

## Required Enhancements

Add a new section to the Admin UI specifically for testing the email alert system with the following features:

1. **Risk Level Simulation**:
   - Display current risk level
   - Provide button to simulate Orange-to-Red transition
   - Ensure this doesn't affect the actual dashboard's risk level display

2. **Test Email Controls**:
   - Select subscribers to receive test emails (only verified emails in AWS SES sandbox)
   - Button to send test emails to selected subscribers
   - Clearly mark test emails to prevent false alarms

3. **Test Results and Logging**:
   - Display status of sent test emails
   - Show any error messages
   - Log test email activity for future reference

## Implementation Steps

1. **Backend Changes**:
   - Create new endpoint in `admin_endpoints.py` for testing emails
   - Add function to simulate risk level transition without affecting dashboard
   - Implement email sending with test markers

2. **Frontend Changes**:
   - Add new card to admin.html for email testing
   - Create selection interface for subscribers
   - Add results display for email sending status
   - Ensure proper UI feedback during email sending process

3. **API Integration**:
   - Ensure proper API calls from frontend to backend
   - Handle error cases and provide clear feedback
   - Maintain PIN authentication security

## Technical Constraints

- Works with existing AWS SES configuration (currently in sandbox mode)
- Only sends to verified email addresses (`overpitch@icloud.com` and `fred@esposto.com`)
- Maintains separation from actual risk level calculation system
- Clear indication in both UI and emails that these are test messages

## Deliverables

1. Modified `admin_endpoints.py` with new testing endpoint
2. Updated `admin.html` with new email testing section
3. Any additional helper functions needed in `email_service.py`
4. Documentation on how to use the new email testing feature

## Testing Plan

1. Test PIN authentication works for the new section
2. Verify test emails are sent properly to verified addresses
3. Confirm that simulating Orange-to-Red transition doesn't affect the actual dashboard
4. Test error handling for various failure scenarios

# Admin UI: Test System Recognition of Red Status - Implementation Plan

## 1. Overview and Purpose

This document outlines the plan to add a new section to the Admin UI titled "Test System Recognition of Red Status." The purpose of this feature is to allow administrators to manually set weather measurement values. This will enable testing of the system's ability to:
1.  Recognize that these manually set values meet the criteria for a "Red" fire risk status.
2.  Act accordingly, including triggering the automatic email alert system.

This feature will help ensure the reliability of the fire risk assessment logic and the subsequent alerting mechanisms under controlled test conditions.

## 2. Affected Components

The implementation will involve changes to the following existing files and the creation of new files:

*   **New Files:**
    *   `static/js/admin_test_conditions.js`: Will contain client-side JavaScript logic for the new UI section.
    *   (Potentially) `events.py`: For a shared event publishing mechanism for SSE.
*   **Modified Files:**
    *   `static/admin.html`: To add the new UI section, update labels, link new JS, and potentially add global admin JS for SSE.
    *   `admin_endpoints.py`: To add new API endpoints for managing manual weather overrides and the SSE notification stream.
    *   `fire_risk_logic.py`: To incorporate manual overrides and return effective weather values.
    *   `cache_refresh.py`: To use effective values for email logic and publish events for SSE.
    *   `email_service.py`: To use effective weather values for email content.
    *   `main.py` (potentially): To initialize the event queue/bus for SSE.
    *   `config.py` (potentially, if new configuration for default thresholds for testing is needed, though current plan is to fetch live thresholds).

## 3. API Endpoints (to be added to `admin_endpoints.py`)

### 3.1. Set/Update Test Conditions

*   **Method:** `POST`
*   **URL:** `/admin/test-conditions`
*   **Request Body (JSON):**
    *   An object containing one or more weather metrics and their manually set values.
    *   Example for setting temperature and humidity: `{"temperature": 76, "humidity": 14}`
*   **Server Action:**
    *   Validates the input.
    *   Stores the provided metric overrides in the admin's server-side session (e.g., `session['manual_weather_overrides']`).
*   **Response:**
    *   Success (e.g., `200 OK`): `{"status": "success", "message": "Test conditions updated."}`
    *   Failure (e.g., `400 Bad Request`): `{"status": "error", "message": "Invalid data provided."}`

### 3.2. Clear Test Conditions

*   **Method:** `DELETE`
*   **URL:** `/admin/test-conditions`
*   **Request Body:** None
*   **Server Action:**
    *   Clears any active `manual_weather_overrides` from the admin's server-side session.
*   **Response:**
    *   Success (e.g., `200 OK`): `{"status": "success", "message": "Test conditions cleared."}`
    *   Failure (e.g., `500 Internal Server Error`): `{"status": "error", "message": "Failed to clear test conditions."}`

### 3.3. SSE Notifications Stream (New)

*   **Method:** `GET`
*   **URL:** `/admin/sse-notifications`
*   **Server Action:**
    *   Establishes a Server-Sent Events stream.
    *   Subscribes to an internal application event queue/bus.
    *   When relevant events (e.g., "email_sent") are published internally, formats them as SSE messages and sends them to the connected client.
    *   Example SSE message: `data: {"type": "email_sent", "count": 2, "message": "Red alert emails sent to 2 subscribers."}\n\n`
*   **Response:** `text/event-stream` content type.

## 4. Server-Side Logic Changes

### 4.1. Session Management for Overrides

*   Flask's server-side session mechanism will store `manual_weather_overrides`.
*   Overrides are session-specific and cleared on session expiry or manual logout.

### 4.2. `fire_risk_logic.py` Modifications

*   The `calculate_fire_risk` function will:
    *   Prioritize `manual_overrides` from the session if passed.
    *   Convert Fahrenheit temperature overrides to Celsius for internal comparison.
    *   **Return a tuple: `(risk_level, explanation, effective_weather_values)` where `effective_weather_values` is a dictionary of the actual values (overridden or original) used for the calculation.**

### 4.3. `admin_endpoints.py` Implementation

*   Implement routes for `/admin/test-conditions` (POST, DELETE) and the new `/admin/sse-notifications` (GET SSE stream).
*   Ensure admin authentication for these routes.

### 4.4. `cache_refresh.py` Modifications

*   When `refresh_data_cache` is called with an admin's `session_token` and `current_admin_sessions`:
    *   It will retrieve `manual_weather_overrides` from the specific admin's session.
    *   It will call `calculate_fire_risk`, passing these overrides.
    *   **It will NOT automatically clear the admin's session overrides after a Red trigger.** Clearing is initiated by the client.
    *   If a Red status is triggered by overrides and emails are sent:
        *   It will use the `effective_weather_values` (returned by `calculate_fire_risk`) to provide accurate data to the email service.
        *   It will publish an "email_sent" event to the application's event queue for SSE notification.
*   The `data_cache.fire_risk_data` will reflect the risk calculated with overrides if they are active for the session initiating the refresh.

### 4.5. `email_service.py` Modifications

*   The function responsible for generating email content (e.g., `send_orange_to_red_alert`) will be updated to accept and use the `effective_weather_values` (from `fire_risk_logic.py` via `cache_refresh.py`) to ensure the email content accurately reflects the conditions that triggered the alert.

### 4.6. Event Publishing Mechanism for SSE (New)

*   A simple application-wide event queue/bus will be implemented (e.g., in `main.py` or a new `events.py`).
*   This will include a function like `publish_admin_event(event_data)` that other modules can call.
*   The SSE endpoint in `admin_endpoints.py` will consume events from this queue.

## 5. Client-Side UI and Logic

### 5.1. HTML Structure (`static/admin.html`)

*   (As previously defined, including the "Important" reminder note about test recipients).
*   Consider adding a global area for toast notifications if not already present.

### 5.2. JavaScript Logic (`static/js/admin_test_conditions.js` - New File)

*   (Initialization and existing event handlers as previously defined).
*   **Enhanced Event Handlers ("Set to Threshold", "Set All to Thresholds"):**
    *   After a successful `POST /admin/test-conditions` and subsequent successful `triggerServerRiskRecalculation()` (which calls `GET /fire-risk?wait_for_fresh=true`):
        *   Check if the response from `/fire-risk` indicates a "Red" status.
        *   If "Red", display a message to the admin: "Red status triggered by overrides. Overrides are active. Auto-clearing in 10 seconds. [Clear Manually Now]".
        *   Start a 10-second client-side timer.
        *   When the timer expires, automatically call the existing `handleClearAll()` function.
*   The `handleClearAll()` function will:
    *   Clear "Set Value" cells in the UI.
    *   Send `DELETE /admin/test-conditions`.
    *   Call `triggerServerRiskRecalculation()` to refresh server cache with actual data.

### 5.3. Global Admin JavaScript for SSE Notifications (New)

*   To be included in `static/admin.html` or a shared admin JS file.
*   On admin page load (after PIN validation):
    *   Establish an `EventSource` connection to `/admin/sse-notifications`.
    *   Implement an `onmessage` handler for the `EventSource`.
    *   When an "email_sent" event is received, parse the data and display it using a toast notification function (e.g., `showAdminToast("Emails sent to X subscribers.")`).

## 6. Label Changes in `static/admin.html`

*   (As previously defined).

## 7. Email Alert Behavior

*   (As previously defined, with the enhancement that email content will reflect the conditions that *caused* the alert).

## 8. (New Section) Admin Real-Time Notifications for Email Dispatch (SSE)

This section details the Server-Sent Events mechanism for notifying the admin in real-time when automated emails are dispatched by the system.

*   **Purpose:** Provide immediate feedback to the administrator when the system sends out alert emails, regardless of the specific admin UI page they are currently viewing.
*   **Mechanism:**
    *   **Backend:**
        *   An SSE endpoint (`GET /admin/sse-notifications`) will be established in `admin_endpoints.py`.
        *   An application-level event queue (e.g., a simple list in `main.py` or `events.py` with appropriate thread/async safety if needed) will be used.
        *   When `cache_refresh.py` (after `email_service.py` confirms dispatch) determines emails were sent, it will publish an event (e.g., `{"type": "email_sent", "count": N, "timestamp": "..."}`) to this queue.
        *   The SSE endpoint will monitor this queue and send new events to connected admin clients.
    *   **Frontend:**
        *   Client-side JavaScript (global to the admin interface) will connect to `/admin/sse-notifications` using `EventSource`.
        *   An `onmessage` event handler will parse incoming events.
        *   Upon receiving an "email_sent" event, a non-intrusive toast notification will be displayed to the admin.

## 9. Phased Implementation Approach (Summary) - Updated

1.  **Phase 1:** Detailed Planning & Backend Foundation Design.
    - **Status:** Completed
2.  **Phase 2:** Admin UI - Static Structure, Label Updates, New JS File creation.
    - **Status:** Completed
3.  **Phase 3:** Admin UI - Dynamic Table Rendering (in `admin_test_conditions.js`).
    - **Status:** Completed
4.  **Phase 4:** Admin UI - Implementing Interactivity (button actions, API calls in `admin_test_conditions.js`).
    - **Status:** Completed
5.  **Phase 5:** Backend Implementation - API endpoints, session logic, `fire_risk_logic.py` adaptation (including unit conversion and override logic).
    - **Status:** Completed
6.  **Phase 6 (New/Revised):** Client-Side Auto-Clear & Email Content Enhancement.
    *   Modify `fire_risk_logic.py` to return effective weather values.
    *   Modify `email_service.py` to use effective values for email content.
    *   Implement client-side timer in `static/js/admin_test_conditions.js` for auto-clearing overrides after a Red trigger.
    - **Status:** Pending
7.  **Phase 7 (New):** Admin Real-Time Notifications (SSE for Email Sent).
    *   Implement backend SSE endpoint, event queue, and event publishing in `cache_refresh.py`.
    *   Implement client-side SSE connection and toast notifications.
    - **Status:** Pending
8.  **Phase 8 (was 6):** Integration, Comprehensive Testing & Refinement.
    *   Thoroughly test all new functionalities: override persistence, client-side auto-clear, email content accuracy, SSE notifications, and overall system behavior.
    - **Status:** Pending

This plan provides a structured approach to implementing the "Test System Recognition of Red Status" feature with the requested enhancements.

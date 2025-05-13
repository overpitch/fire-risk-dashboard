# Admin UI: Test System Recognition of Red Status - Implementation Plan

## 1. Overview and Purpose

This document outlines the plan to add a new section to the Admin UI titled "Test System Recognition of Red Status." The purpose of this feature is to allow administrators to manually set weather measurement values. This will enable testing of the system's ability to:
1.  Recognize that these manually set values meet the criteria for a "Red" fire risk status.
2.  Act accordingly, including triggering the automatic email alert system.

This feature will help ensure the reliability of the fire risk assessment logic and the subsequent alerting mechanisms under controlled test conditions.

## 2. Affected Components

The implementation will involve changes to the following existing files and the creation of a new JavaScript file:

*   **New File:**
    *   `static/js/admin_test_conditions.js`: Will contain client-side JavaScript logic for the new UI section.
*   **Modified Files:**
    *   `static/admin.html`: To add the new UI section, update labels, and link the new JS file.
    *   `admin_endpoints.py`: To add new API endpoints for managing manual weather overrides.
    *   `fire_risk_logic.py`: To incorporate manual overrides into the fire risk calculation.
    *   `config.py` (potentially, if new configuration for default thresholds for testing is needed, though current plan is to fetch live thresholds).

## 3. API Endpoints (to be added to `admin_endpoints.py`)

Two new API endpoints will be created to manage the manual weather condition overrides. These endpoints will be protected and require admin authentication.

### 3.1. Set/Update Test Conditions

*   **Method:** `POST`
*   **URL:** `/admin/test-conditions`
*   **Request Body (JSON):**
    *   An object containing one or more weather metrics and their manually set values.
    *   Example for setting temperature and humidity: `{"temperature": 76, "humidity": 14}`
    *   Example for setting only temperature: `{"temperature": 76}`
*   **Server Action:**
    *   Validates the input.
    *   Stores the provided metric overrides in the admin's server-side session (e.g., `session['manual_weather_overrides'] = {"temperature": 76, "humidity": 14}`). If overrides already exist in the session, they are updated with the new values.
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

## 4. Server-Side Logic Changes

### 4.1. Session Management for Overrides

*   Flask's server-side session mechanism will be used to store the manual weather overrides.
*   The overrides will be stored under a specific session key, for example, `session['manual_weather_overrides']`.
*   This dictionary will map metric names (e.g., "temperature", "humidity") to their overridden numerical values.
*   These overrides are specific to the admin's session and will be cleared when the session ends (logout, browser close, session expiry).

### 4.2. `fire_risk_logic.py` Modifications

*   The core fire risk calculation function (e.g., `calculate_fire_risk` or equivalent) will be modified.
*   **Priority of Overrides:** Before fetching live data or using regularly cached data for weather metrics, the function will check if `session.get('manual_weather_overrides')` exists and contains relevant entries.
*   **Applying Overrides:**
    *   If an override exists for a specific metric (e.g., temperature), that overridden value will be used in the risk calculation instead of the live/cached value.
    *   Metrics *not* present in the `manual_weather_overrides` dictionary will continue to use their normal data sources (live API data or regular cache).
*   This ensures that the admin can test the impact of specific conditions without affecting all data points.

### 4.3. `admin_endpoints.py` Implementation

*   The new routes (`/admin/test-conditions` for `POST` and `DELETE`) will be implemented.
*   These routes will handle the logic for updating and clearing the `manual_weather_overrides` in the session.
*   Appropriate admin authentication/authorization checks will be applied to these endpoints.

## 5. Client-Side UI and Logic

### 5.1. HTML Structure (`static/admin.html`)

*   **New Section:**
    *   A new accordion item within the "Testing" accordion group will be added.
    *   Title: "Test System Recognition of Red Status".
    *   Placement: This new section will be placed *after* the existing two sections ("Test System Operation Using Cached Data" and "Test Sending Red-Alert Emails").
*   **Table Structure (within the new section):**
    *   The table design will be based on the provided mockup and will extend the structure of the "Current Weather Conditions" table from the main dashboard.
    *   **Header Row:** Will contain global action buttons:
        *   "Clear All"
        *   "Set All to Thresholds"
    *   **Column Headers:**
        1.  Metric Name (e.g., "Temperature")
        2.  Current Value (displaying live/cached data, read-only for the admin in this context)
        3.  Thresholds (e.g., ">75°F")
        4.  Set Value (input field or display area for the manually overridden value, initially blank)
        5.  Action (containing the "Set to Threshold" button for each metric row)
    *   **Metric Rows:** Rows for:
        *   Temperature
        *   Humidity
        *   Average Winds
        *   Wind Gust
        *   Soil Moisture (15cm depth)
*   **Admin Reminder Note:**
    *   A clearly visible text note will be added within this new section:
        >   "**Important:** Before triggering a Red status test that sends emails, ensure your subscriber list is configured with appropriate test recipients to avoid sending alerts to all real subscribers."
*   **JavaScript Link:**
    *   A script tag will be added to link the new `static/js/admin_test_conditions.js` file.

### 5.2. JavaScript Logic (`static/js/admin_test_conditions.js` - New File)

*   **Initialization (`initTestConditionsTable` function):**
    *   On page load (or when the accordion section is expanded), fetch current operational weather thresholds. These are available in the response from the `/fire-risk` endpoint (in the `data.thresholds` object).
    *   Dynamically render the HTML table structure described above.
    *   Populate the "Current Value" column by fetching current weather data (e.g., from `/fire-risk`).
    *   Populate the "Thresholds" column using the fetched threshold data.
    *   The "Set Value" column for all metrics will be initially blank.
*   **Event Handlers:**
    *   **"Set to Threshold" button (per metric row):**
        1.  When clicked, calculate the target override value based on the metric's threshold (e.g., if threshold is `>75°F`, set value to `76`).
        2.  Update the corresponding "Set Value" cell in the UI to display this new override.
        3.  Send a `POST` request to `/admin/test-conditions` with a JSON body containing the single metric and its new override value (e.g., `{"temperature": 76}`).
    *   **"Set All to Thresholds" button:**
        1.  When clicked, calculate target override values for all five metrics.
        2.  Update all "Set Value" cells in the UI.
        3.  Send a `POST` request to `/admin/test-conditions` with a JSON body containing all five metric overrides.
    *   **"Clear All" button:**
        1.  When clicked, clear the content of all "Set Value" cells in the UI (make them blank).
        2.  Send a `DELETE` request to `/admin/test-conditions`.
*   **UI Updates:** The UI should dynamically reflect the success or failure of API calls (e.g., by showing a temporary status message).

## 6. Label Changes in `static/admin.html`

The following labels in the "Testing" accordion section will be updated:
*   "Test Mode" will be renamed to "Test System Operation Using Cached Data".
*   "Test Orange-to-Red Alert Emails" will be renamed to "Test Sending Red-Alert Emails".

## 7. Email Alert Behavior

*   If the manual overrides set by the admin cause the `fire_risk_logic.py` to determine a "Red" status, the system will proceed to initiate the email alert process.
*   These email alerts will be sent to the recipients listed in the **currently active subscriber database**. It is the admin's responsibility to manage this list appropriately for testing purposes, as highlighted by the reminder note in the UI.

## 8. Phased Implementation Approach (Summary)

1.  **Phase 1 (Current):** Detailed Planning & Backend Foundation Design (this document).
    - **Status:** Completed
2.  **Phase 2:** Admin UI - Static Structure, Label Updates, New JS File creation.
    - **Status:** Completed
3.  **Phase 3:** Admin UI - Dynamic Table Rendering (in `admin_test_conditions.js`).
    - **Status:** Completed
4.  **Phase 4:** Admin UI - Implementing Interactivity (button actions, API calls in `admin_test_conditions.js`).
    - **Status:** Completed
5.  **Phase 5:** Backend Implementation - API endpoints, session logic, `fire_risk_logic.py` adaptation.
    - **Status:** Completed
6.  **Phase 6:** Integration, Comprehensive Testing & Refinement.
    - **Status:** Pending

This plan provides a structured approach to implementing the "Test System Recognition of Red Status" feature.

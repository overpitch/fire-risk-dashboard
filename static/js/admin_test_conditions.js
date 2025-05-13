const METRICS_CONFIG = [
    { id: 'temperature', displayName: 'Temperature', unit: '°F', thresholdKey: 'temp', comparison: '>', currentValueKey: 'air_temp', apiKey: 'temperature' },
    { id: 'humidity', displayName: 'Humidity', unit: '%', thresholdKey: 'humid', comparison: '<', currentValueKey: 'relative_humidity', apiKey: 'humidity' },
    { id: 'avg_wind_speed', displayName: 'Average Winds', unit: 'mph', thresholdKey: 'wind', comparison: '>', currentValueKey: 'wind_speed', apiKey: 'average_winds' },
    { id: 'wind_gust', displayName: 'Wind Gust', unit: 'mph', thresholdKey: 'gusts', comparison: '>', currentValueKey: 'wind_gust', apiKey: 'wind_gust' },
    { id: 'soil_moisture_15cm', displayName: 'Soil Moisture (15cm depth)', unit: '%', thresholdKey: 'soil_moist', comparison: '<', currentValueKey: 'soil_moisture_15cm', apiKey: 'soil_moisture' }
];

let currentFetchedThresholds = null;
let currentMetricConfigurations = {}; // Will store processed config with actual threshold values
let autoClearTimerId = null; // Timer for auto-clearing overrides

// Helper function to display feedback messages
function displayFeedbackMessage(message, type = 'info', duration = 5000) {
    const feedbackDiv = document.getElementById('admin-test-conditions-feedback');
    if (!feedbackDiv) {
        console.error('Feedback div #admin-test-conditions-feedback not found.');
        return;
    }
    feedbackDiv.className = `alert alert-${type === 'error' ? 'danger' : (type === 'success' ? 'success' : 'info')} mt-2`;
    feedbackDiv.innerHTML = message; // Use innerHTML to allow for clickable elements
    feedbackDiv.style.display = 'block';

    setTimeout(() => {
        feedbackDiv.style.display = 'none';
        feedbackDiv.innerHTML = ''; // Clear innerHTML
    }, duration);
}

// Helper function to calculate override value
function calculateOverrideValue(thresholdValue, comparisonOperator, unit) {
    let numericThreshold = parseFloat(thresholdValue);
    if (isNaN(numericThreshold)) return null; // Should not happen if data is clean

    let overrideValue;
    if (comparisonOperator === '>') {
        overrideValue = numericThreshold + 1;
    } else if (comparisonOperator === '<') {
        overrideValue = numericThreshold - 1;
    } else {
        return null; // Unknown comparison
    }

    // Ensure humidity stays within 0-100%
    if (unit === '%') {
        if (overrideValue < 0) overrideValue = 0;
        if (overrideValue > 100) overrideValue = 100;
    }
    // For temperature, we might want to ensure it's an integer if thresholds are integers
    if (unit === '°F' && Number.isInteger(numericThreshold)) {
        overrideValue = Math.round(overrideValue);
    }

    return overrideValue;
}

// Helper function for API calls
async function callTestConditionsApi(method, body = null) {
    try {
        const options = {
            method: method,
            headers: {},
            credentials: 'include'
        };
        if (body) {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(body);
        }

        const response = await fetch('/admin/test-conditions', options);
        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.message || `API request failed with status ${response.status}`);
        }
        return result;
    } catch (error) {
        console.error(`API call error (${method}):`, error);
        displayFeedbackMessage(`API Error: ${error.message}`, 'error');
        return null; // Or throw error to be caught by caller
    }
}

// Event Handlers
async function handleSetIndividualThreshold(event) {
    const metricId = event.target.dataset.metric;
    const metricConfig = currentMetricConfigurations[metricId];

    if (!metricConfig || metricConfig.thresholdValue === undefined || metricConfig.thresholdValue === null) {
        displayFeedbackMessage(`Threshold data not available for ${metricConfig ? metricConfig.displayName : metricId}.`, 'error');
        return;
    }

    const overrideValue = calculateOverrideValue(metricConfig.thresholdValue, metricConfig.comparison, metricConfig.unit);
    if (overrideValue === null) {
        displayFeedbackMessage(`Could not calculate override for ${metricConfig.displayName}.`, 'error');
        return;
    }

    const setValueCell = document.getElementById(`set-value-${metricId}`);
    if (setValueCell) {
        setValueCell.textContent = `${overrideValue}${metricConfig.unit}`;
    }

    const apiPayload = { [metricConfig.apiKey]: overrideValue };
    const result = await callTestConditionsApi('POST', apiPayload);

    if (result && result.status === 'success') {
        // displayFeedbackMessage(`${metricConfig.displayName} override sent. ${result.message || ''}`, 'success');
        // triggerServerRiskRecalculation(); // Trigger recalculation
        await handlePostOverrideRecalculation(`${metricConfig.displayName} override sent. ${result.message || ''}`);
    } else if (result) {
        displayFeedbackMessage(`Failed to set ${metricConfig.displayName}. ${result.message || ''}`, 'error');
        // Optionally revert UI: if (setValueCell) setValueCell.textContent = '';
    }
    // If result is null, callTestConditionsApi already showed an error
}

async function handleSetAllThresholds() {
    const allOverridesPayload = {};
    let allOverridesCalculated = true;

    METRICS_CONFIG.forEach(metric => {
        const metricConfig = currentMetricConfigurations[metric.id];
        if (!metricConfig || metricConfig.thresholdValue === undefined || metricConfig.thresholdValue === null) {
            displayFeedbackMessage(`Threshold data not available for ${metricConfig ? metricConfig.displayName : metric.id}. Cannot set all.`, 'error');
            allOverridesCalculated = false;
            return; // from forEach callback
        }

        const overrideValue = calculateOverrideValue(metricConfig.thresholdValue, metricConfig.comparison, metricConfig.unit);
        if (overrideValue === null) {
            displayFeedbackMessage(`Could not calculate override for ${metricConfig.displayName}. Cannot set all.`, 'error');
            allOverridesCalculated = false;
            return; // from forEach callback
        }

        const setValueCell = document.getElementById(`set-value-${metric.id}`);
        if (setValueCell) {
            setValueCell.textContent = `${overrideValue}${metricConfig.unit}`;
        }
        allOverridesPayload[metricConfig.apiKey] = overrideValue;
    });

    if (!allOverridesCalculated || Object.keys(allOverridesPayload).length !== METRICS_CONFIG.length) {
        // An error message would have already been displayed by the loop
        return;
    }

    const result = await callTestConditionsApi('POST', allOverridesPayload);
    if (result && result.status === 'success') {
        // displayFeedbackMessage(`All metric overrides sent. ${result.message || ''}`, 'success');
        // triggerServerRiskRecalculation(); // Trigger recalculation
        await handlePostOverrideRecalculation(`All metric overrides sent. ${result.message || ''}`);
    } else if (result) {
        displayFeedbackMessage(`Failed to set all overrides. ${result.message || ''}`, 'error');
        // Optionally revert all UI changes
    }
}

async function handleClearAll() {
    if (autoClearTimerId) {
        clearTimeout(autoClearTimerId);
        autoClearTimerId = null;
        console.log("Auto-clear timer cancelled by handleClearAll.");
    }
    METRICS_CONFIG.forEach(metric => {
        const setValueCell = document.getElementById(`set-value-${metric.id}`);
        if (setValueCell) {
            setValueCell.textContent = '';
        }
    });

    const apiCallResult = await callTestConditionsApi('DELETE'); // Renamed to avoid conflict
    if (apiCallResult && apiCallResult.status === 'success') {
        displayFeedbackMessage(`All overrides cleared. ${apiCallResult.message || ''}`, 'success');
        // Now, await recalculation and process its result for email feedback
        const fireRiskData = await triggerServerRiskRecalculation();
        if (fireRiskData && fireRiskData.email_send_outcome) {
            console.log('handleClearAll - Email send outcome from server:', fireRiskData.email_send_outcome);
            switch (fireRiskData.email_send_outcome) {
                case 'success':
                    displayFeedbackMessage('Alert email sent successfully.', 'success', 5000);
                    break;
                case 'failed':
                    displayFeedbackMessage('Failed to send alert email.', 'error', 5000);
                    break;
                case 'not_triggered_no_recipients':
                    displayFeedbackMessage('Email alert not sent: No active subscribers.', 'info', 5000);
                    break;
                case 'not_triggered_conditions_met':
                    console.log('handleClearAll - Email alert not triggered: Conditions for sending not met.');
                    break;
                default:
                    console.log('handleClearAll - Unknown email_send_outcome:', fireRiskData.email_send_outcome);
                    break;
            }
        } else if (fireRiskData) {
            console.log('handleClearAll - fireRiskData does not contain email_send_outcome field.');
        } else {
            console.log('handleClearAll - fireRiskData was null after clearing overrides.');
        }
    } else if (apiCallResult) {
        displayFeedbackMessage(`Failed to clear overrides. ${apiCallResult.message || ''}`, 'error');
    }
}

// Function to force server-side recalculation of fire risk using current (potentially overridden) conditions
async function triggerServerRiskRecalculation() {
    console.log('Triggering server-side risk recalculation with wait_for_fresh=true');
    try {
        const response = await fetch('/fire-risk?wait_for_fresh=true', { credentials: 'include' });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ message: `HTTP error ${response.status}` }));
            throw new Error(errorData.message || `Failed to trigger server risk recalculation. Status: ${response.status}`);
        }
        const data = await response.json();
        console.log('Server risk recalculation triggered successfully. New status:', data.risk);
        // displayFeedbackMessage('Server risk status updated.', 'info', 2000); 
        return data; // Return the full data object
    } catch (error) {
        console.error('Error triggering server risk recalculation:', error);
        displayFeedbackMessage(`Error updating server risk status: ${error.message}`, 'error');
        return null; // Indicate failure
    }
}

// New function to handle manual clear from feedback message
function handleClearAllAndStopTimer() {
    console.log("Manual clear triggered from feedback message.");
    if (autoClearTimerId) {
        clearTimeout(autoClearTimerId);
        autoClearTimerId = null;
        console.log("Auto-clear timer cancelled.");
    }
    handleClearAll(); // Call the existing clear all logic
}


// New helper function for post-override logic
async function handlePostOverrideRecalculation(baseSuccessMessage) {
    console.log('Entering handlePostOverrideRecalculation. Base message:', baseSuccessMessage); // Initial entry log
    const fireRiskData = await triggerServerRiskRecalculation();
    console.log('handlePostOverrideRecalculation - fireRiskData object:', fireRiskData); // Log the object directly

    if (fireRiskData && fireRiskData.risk === 'Red') {
        if (autoClearTimerId) {
            clearTimeout(autoClearTimerId); // Clear any pre-existing timer
        }
        const feedbackMessage = `${baseSuccessMessage} Red status triggered by overrides. Overrides are active. Auto-clearing in 10 seconds. You can also <span class='text-primary fw-bold' style='cursor:pointer;' onclick='handleClearAllAndStopTimer()'>Clear Manually Now</span>.`;
        displayFeedbackMessage(feedbackMessage, 'warning', 12000); // Longer duration for this message

        autoClearTimerId = setTimeout(() => {
            console.log("Auto-clear timer expired. Calling handleClearAll().");
            displayFeedbackMessage('Auto-clearing overrides now...', 'info', 3000);
            handleClearAll();
            autoClearTimerId = null; // Reset timer ID
        }, 10000); // 10 seconds
    } else if (fireRiskData) {
        // Not Red, or some other status. Just show success for override.
        displayFeedbackMessage(`${baseSuccessMessage} Server risk status is now ${fireRiskData.risk || 'unknown'}.`, 'success');
    } else if (fireRiskData === null) { // Explicitly check for null if triggerServerRiskRecalculation failed
        // triggerServerRiskRecalculation failed, error already shown by it.
        displayFeedbackMessage(`${baseSuccessMessage} However, failed to confirm new risk status.`, 'warning');
    }
    // This part will execute regardless of the 'Red' status, if fireRiskData is not null

    // Display email send outcome if available
    if (fireRiskData) { 
        // console.log('handlePostOverrideRecalculation - fireRiskData received (stringified):', JSON.stringify(fireRiskData, null, 2)); // Keep this commented for now
        if (fireRiskData.email_send_outcome) {
            console.log('handlePostOverrideRecalculation - Email send outcome from server:', fireRiskData.email_send_outcome);
            switch (fireRiskData.email_send_outcome) {
                case 'success':
                    console.log('handlePostOverrideRecalculation - Displaying email success message.');
                    displayFeedbackMessage('Alert email sent successfully.', 'success', 5000);
                    break;
                case 'failed':
                    console.log('handlePostOverrideRecalculation - Displaying email failed message.');
                    displayFeedbackMessage('Failed to send alert email.', 'error', 5000);
                    break;
                case 'not_triggered_no_recipients':
                    console.log('handlePostOverrideRecalculation - Displaying email not_triggered_no_recipients message.');
                    displayFeedbackMessage('Email alert not sent: No active subscribers.', 'info', 5000);
                    break;
                case 'not_triggered_conditions_met':
                    console.log('handlePostOverrideRecalculation - Email alert not triggered: Conditions for sending not met (e.g., not Orange to Red, or already alerted today).');
                    // No UI message for this case by design, but log is helpful.
                    break;
                default:
                    console.log('handlePostOverrideRecalculation - Unknown email_send_outcome:', fireRiskData.email_send_outcome);
                    break;
            }
        } else {
            console.log('handlePostOverrideRecalculation - fireRiskData does not contain email_send_outcome field.');
        }
    } else { // This means fireRiskData is null
        console.log('handlePostOverrideRecalculation - fireRiskData was null, so no email outcome check.');
    }
}

// Function to attach event listeners
function attachTestConditionsEventListeners() {
    const clearAllBtn = document.getElementById('clear-all-btn');
    if (clearAllBtn) {
        clearAllBtn.addEventListener('click', handleClearAll);
    }

    const setAllToThresholdsBtn = document.getElementById('set-all-to-thresholds-btn');
    if (setAllToThresholdsBtn) {
        setAllToThresholdsBtn.addEventListener('click', handleSetAllThresholds);
    }

    METRICS_CONFIG.forEach(metric => {
        const setButton = document.getElementById(`set-to-threshold-${metric.id}-btn`);
        if (setButton) {
            setButton.addEventListener('click', handleSetIndividualThreshold);
        }
    });

    // Event listener for the new email limit toggle
    const emailLimitToggle = document.getElementById('ignoreEmailDailyLimitToggle');
    if (emailLimitToggle) {
        emailLimitToggle.addEventListener('change', handleEmailLimitToggleChange);
    }
}


async function initTestConditionsTable() {
    const tableContainer = document.getElementById('admin-test-conditions-table-container');
    if (!tableContainer) {
        console.error('Error: Test conditions table container not found.');
        return;
    }

    // Ensure feedback div exists or create it
    let feedbackDiv = document.getElementById('admin-test-conditions-feedback');
    if (!feedbackDiv) {
        feedbackDiv = document.createElement('div');
        feedbackDiv.id = 'admin-test-conditions-feedback';
        feedbackDiv.className = 'mt-2';
        feedbackDiv.style.display = 'none'; // Initially hidden
        // Insert it before the table container, or adjust as needed
        tableContainer.parentNode.insertBefore(feedbackDiv, tableContainer);
    }


    tableContainer.innerHTML = '<p>Loading test conditions data...</p>'; // Placeholder while fetching

    try {
        const response = await fetch('/fire-risk');
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }
        const apiData = await response.json();

        if (!apiData.thresholds || !apiData.weather) { // Check for thresholds and weather directly on apiData
            throw new Error('Invalid data structure from /fire-risk endpoint. Expected "thresholds" and "weather" properties.');
        }

        currentFetchedThresholds = apiData.thresholds; // Access directly from apiData
        const currentWeatherData = apiData.weather;   // Access directly from apiData

        // Populate currentMetricConfigurations
        currentMetricConfigurations = {}; // Reset
        METRICS_CONFIG.forEach(metric => {
            currentMetricConfigurations[metric.id] = {
                ...metric, // Spread original config
                thresholdValue: currentFetchedThresholds[metric.thresholdKey] // Add actual threshold value
            };
        });


        // Clear placeholder
        tableContainer.innerHTML = '';

        // Create table
        const table = document.createElement('table');
        table.className = 'table table-striped table-bordered table-sm';

        // Table Head - Global Actions
        const theadGlobal = table.createTHead();
        const globalActionRow = theadGlobal.insertRow();
        const globalActionCell = globalActionRow.insertCell();
        globalActionCell.colSpan = 5;
        globalActionCell.className = 'text-end';

        const clearAllBtn = document.createElement('button');
        clearAllBtn.id = 'clear-all-btn';
        clearAllBtn.className = 'btn btn-sm btn-outline-danger me-2';
        clearAllBtn.textContent = 'Clear All';
        globalActionCell.appendChild(clearAllBtn);

        const setAllToThresholdsBtn = document.createElement('button');
        setAllToThresholdsBtn.id = 'set-all-to-thresholds-btn';
        setAllToThresholdsBtn.className = 'btn btn-sm btn-outline-primary';
        setAllToThresholdsBtn.textContent = 'Set All to Thresholds';
        globalActionCell.appendChild(setAllToThresholdsBtn);

        // Table Head - Column Headers
        const thead = table.createTHead();
        const headerRow = thead.insertRow();
        const headers = ['Metric Name', 'Current Value', 'Thresholds', 'Set Value', 'Action'];
        headers.forEach(headerText => {
            const th = document.createElement('th');
            th.textContent = headerText;
            headerRow.appendChild(th);
        });

        // Table Body
        const tbody = table.createTBody();
        METRICS_CONFIG.forEach(metric => {
            const row = tbody.insertRow();
            const metricFullConfig = currentMetricConfigurations[metric.id]; // Use the processed config

            // Metric Name
            row.insertCell().textContent = metricFullConfig.displayName;

            // Current Value
            const currentValue = currentWeatherData[metricFullConfig.currentValueKey];
            row.insertCell().textContent = (currentValue !== undefined && currentValue !== null) ? `${currentValue}${metricFullConfig.unit}` : 'N/A';

            // Thresholds
            const thresholdDisplayValue = metricFullConfig.thresholdValue;
            row.insertCell().innerHTML = (thresholdDisplayValue !== undefined && thresholdDisplayValue !== null) ? `${metricFullConfig.comparison}${thresholdDisplayValue}${metricFullConfig.unit}` : 'N/A';

            // Set Value (initially blank)
            const setValueCell = row.insertCell();
            setValueCell.id = `set-value-${metricFullConfig.id}`;
            setValueCell.textContent = '';

            // Action
            const actionCell = row.insertCell();
            const setButton = document.createElement('button');
            setButton.id = `set-to-threshold-${metricFullConfig.id}-btn`;
            setButton.className = 'btn btn-sm btn-outline-secondary';
            setButton.textContent = 'Set to Threshold';
            setButton.setAttribute('data-metric', metricFullConfig.id);
            actionCell.appendChild(setButton);
        });

        tableContainer.appendChild(table);
        attachTestConditionsEventListeners(); // Attach listeners after table is in DOM

    } catch (error) {
        console.error('Error initializing test conditions table:', error);
        tableContainer.innerHTML = `<div class="alert alert-danger">Failed to load test conditions table: ${error.message}</div>`;
        // Also display in feedback div if it exists
        displayFeedbackMessage(`Error initializing table: ${error.message}`, 'error');
    }
}

// Initialize table when the "Testing" accordion section is shown
document.addEventListener('DOMContentLoaded', () => {
    const testingAccordion = document.getElementById('collapseTesting');
    let tableInitialized = false; // Flag to ensure table is initialized only once per show
    let emailLimitToggleInitialized = false; // Flag for the new toggle

    async function initializeTestingSection() {
        if (document.getElementById('admin-test-conditions-table-container') && !tableInitialized) {
            console.log('Initializing test conditions table.');
            await initTestConditionsTable(); // Make sure it can be awaited if it becomes async
            tableInitialized = true;
        }
        if (document.getElementById('ignoreEmailDailyLimitToggle') && !emailLimitToggleInitialized) {
            console.log('Initializing email daily limit toggle.');
            await fetchEmailLimitStatus(); // Fetch initial status
            // Event listener is attached in attachTestConditionsEventListeners, which is called by initTestConditionsTable
            // If initTestConditionsTable isn't called (e.g. if only toggle exists), we might need to call attach separately.
            // For now, assuming initTestConditionsTable will always run if the section is visible.
            // We also need to ensure attachTestConditionsEventListeners is called if only the toggle is present.
            // Let's ensure event listeners are attached regardless.
            attachTestConditionsEventListeners(); // Call it here to be sure if table init is skipped for some reason
            emailLimitToggleInitialized = true;
        }
    }

    if (testingAccordion) {
        testingAccordion.addEventListener('show.bs.collapse', function () {
            initializeTestingSection();
        });

        // If the Testing accordion is already open on page load, initialize components.
        if (testingAccordion.classList.contains('show')) {
            console.log('Testing accordion is already open on load, initializing components.');
            initializeTestingSection();
        }
    } else {
        console.warn('#collapseTesting element not found for event listener for test conditions table and email limit toggle.');
    }
});

// --- Email Daily Limit Toggle Functions ---

async function fetchEmailLimitStatus() {
    const toggle = document.getElementById('ignoreEmailDailyLimitToggle');
    const feedbackDiv = document.getElementById('emailLimitToggleFeedback');
    if (!toggle || !feedbackDiv) {
        console.error('Email limit toggle or feedback div not found.');
        return;
    }

    try {
        feedbackDiv.textContent = 'Loading status...';
        const response = await fetch('/admin/settings/email-limit-status', { credentials: 'include' });
        const result = await response.json();

        if (response.ok && result.status === 'success') {
            toggle.checked = result.ignore_email_daily_limit;
            feedbackDiv.textContent = `Current setting: ${result.ignore_email_daily_limit ? 'Ignoring daily limit' : 'Abiding by daily limit'}.`;
            setTimeout(() => { feedbackDiv.textContent = ''; }, 3000);
        } else {
            throw new Error(result.message || 'Failed to fetch email limit status.');
        }
    } catch (error) {
        console.error('Error fetching email limit status:', error);
        feedbackDiv.innerHTML = `<span class="text-danger">Error: ${error.message}</span>`;
    }
}

async function handleEmailLimitToggleChange(event) {
    const toggle = event.target;
    const feedbackDiv = document.getElementById('emailLimitToggleFeedback');
    if (!feedbackDiv) return;

    const ignoreDailyLimit = toggle.checked;
    feedbackDiv.textContent = 'Updating setting...';

    try {
        const response = await fetch('/admin/settings/email-limit', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({ ignore_daily_limit: ignoreDailyLimit }),
            credentials: 'include'
        });
        const result = await response.json();

        if (response.ok && result.status === 'success') {
            feedbackDiv.innerHTML = `<span class="text-success">${result.message}</span>`;
        } else {
            throw new Error(result.message || 'Failed to update email limit setting.');
        }
    } catch (error) {
        console.error('Error updating email limit setting:', error);
        feedbackDiv.innerHTML = `<span class="text-danger">Error: ${error.message}</span>`;
        // Revert toggle on error
        toggle.checked = !ignoreDailyLimit;
    } finally {
        setTimeout(() => { 
            // Refetch status to be sure, or just clear message
            // fetchEmailLimitStatus(); // Or simply clear
            if (feedbackDiv.innerHTML.includes('Error:')) {
                 // Keep error message longer or until next successful load
            } else {
                feedbackDiv.textContent = '';
            }
        }, 4000);
    }
}

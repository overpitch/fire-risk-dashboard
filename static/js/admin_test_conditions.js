const METRICS_CONFIG = [
    { id: 'temperature', displayName: 'Temperature', unit: '°F', thresholdKey: 'temp', comparison: '>', currentValueKey: 'air_temp', apiKey: 'temperature' },
    { id: 'humidity', displayName: 'Humidity', unit: '%', thresholdKey: 'humid', comparison: '<', currentValueKey: 'relative_humidity', apiKey: 'humidity' },
    { id: 'avg_wind_speed', displayName: 'Average Winds', unit: 'mph', thresholdKey: 'wind', comparison: '>', currentValueKey: 'wind_speed', apiKey: 'average_winds' },
    { id: 'wind_gust', displayName: 'Wind Gust', unit: 'mph', thresholdKey: 'gusts', comparison: '>', currentValueKey: 'wind_gust', apiKey: 'wind_gust' },
    { id: 'soil_moisture_15cm', displayName: 'Soil Moisture (15cm depth)', unit: '%', thresholdKey: 'soil_moist', comparison: '<', currentValueKey: 'soil_moisture_15cm', apiKey: 'soil_moisture' }
];

let currentFetchedThresholds = null;
let currentMetricConfigurations = {}; // Will store processed config with actual threshold values

// Helper function to display feedback messages
function displayFeedbackMessage(message, type = 'info', duration = 5000) {
    const feedbackDiv = document.getElementById('admin-test-conditions-feedback');
    if (!feedbackDiv) {
        console.error('Feedback div #admin-test-conditions-feedback not found.');
        return;
    }
    feedbackDiv.className = `alert alert-${type === 'error' ? 'danger' : (type === 'success' ? 'success' : 'info')} mt-2`;
    feedbackDiv.textContent = message;
    feedbackDiv.style.display = 'block';

    setTimeout(() => {
        feedbackDiv.style.display = 'none';
        feedbackDiv.textContent = '';
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
        displayFeedbackMessage(`${metricConfig.displayName} override sent. ${result.message || ''}`, 'success');
        triggerServerRiskRecalculation(); // Trigger recalculation
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
        displayFeedbackMessage(`All metric overrides sent. ${result.message || ''}`, 'success');
        triggerServerRiskRecalculation(); // Trigger recalculation
    } else if (result) {
        displayFeedbackMessage(`Failed to set all overrides. ${result.message || ''}`, 'error');
        // Optionally revert all UI changes
    }
}

async function handleClearAll() {
    METRICS_CONFIG.forEach(metric => {
        const setValueCell = document.getElementById(`set-value-${metric.id}`);
        if (setValueCell) {
            setValueCell.textContent = '';
        }
    });

    const result = await callTestConditionsApi('DELETE');
    if (result && result.status === 'success') {
        displayFeedbackMessage(`All overrides cleared. ${result.message || ''}`, 'success');
        triggerServerRiskRecalculation(); // Trigger recalculation
    } else if (result) {
        displayFeedbackMessage(`Failed to clear overrides. ${result.message || ''}`, 'error');
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
        console.log('Server risk recalculation triggered successfully. New status (if changed) is now cached.', data.risk);
        // Optionally, display a subtle feedback that server state is updated
        // displayFeedbackMessage('Server risk status updated.', 'info', 2000);
    } catch (error) {
        console.error('Error triggering server risk recalculation:', error);
        displayFeedbackMessage(`Error updating server risk status: ${error.message}`, 'error');
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

    if (testingAccordion) {
        testingAccordion.addEventListener('show.bs.collapse', function () {
            // Check if the table container exists within the now visible accordion body
            if (document.getElementById('admin-test-conditions-table-container')) {
                console.log('Testing accordion shown, initializing test conditions table.');
                // Only initialize if not already done, or if we want to re-initialize every time it's shown
                // For now, let's assume we initialize it once when it's first shown.
                // If re-initialization on every show is desired, remove the tableInitialized check.
                if (!tableInitialized) {
                    initTestConditionsTable();
                    tableInitialized = true; 
                }
            }
        });

        // If the Testing accordion is already open on page load, initialize the table.
        if (testingAccordion.classList.contains('show')) {
            if (document.getElementById('admin-test-conditions-table-container')) {
                console.log('Testing accordion is already open on load, initializing test conditions table.');
                initTestConditionsTable();
                tableInitialized = true;
            }
        }
    } else {
        console.warn('#collapseTesting element not found for event listener for test conditions table.');
    }
});

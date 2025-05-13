const METRICS_CONFIG = [
    { id: 'temperature', displayName: 'Temperature', unit: '°F', thresholdKey: 'temperature_gt', comparison: '>', currentValueKey: 'temperature' },
    { id: 'humidity', displayName: 'Humidity', unit: '%', thresholdKey: 'humidity_lt', comparison: '<', currentValueKey: 'humidity' }, // Use < for <
    { id: 'avg_wind_speed', displayName: 'Average Winds', unit: 'mph', thresholdKey: 'avg_wind_speed_gt', comparison: '>', currentValueKey: 'avg_wind_speed' },
    { id: 'wind_gust', displayName: 'Wind Gust', unit: 'mph', thresholdKey: 'wind_gust_gt', comparison: '>', currentValueKey: 'wind_gust' },
    { id: 'soil_moisture_15cm', displayName: 'Soil Moisture (15cm depth)', unit: '%', thresholdKey: 'soil_moisture_15cm_lt', comparison: '<', currentValueKey: 'soil_moisture_15cm' }
];

async function initTestConditionsTable() {
    const tableContainer = document.getElementById('admin-test-conditions-table-container');
    if (!tableContainer) {
        console.error('Error: Test conditions table container not found.');
        return;
    }

    tableContainer.innerHTML = '<p>Loading test conditions data...</p>'; // Placeholder while fetching

    try {
        const response = await fetch('/fire-risk');
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }
        const apiData = await response.json();

        if (!apiData.data || !apiData.data.thresholds || !apiData.data.weather) {
            throw new Error('Invalid data structure from /fire-risk endpoint.');
        }

        const thresholds = apiData.data.thresholds;
        const currentWeatherData = apiData.data.weather;

        // Clear placeholder
        tableContainer.innerHTML = '';

        // Create table
        const table = document.createElement('table');
        table.className = 'table table-striped table-bordered table-sm'; // Added table-sm for compactness

        // Table Head - Global Actions
        const theadGlobal = table.createTHead();
        const globalActionRow = theadGlobal.insertRow();
        const globalActionCell = globalActionRow.insertCell();
        globalActionCell.colSpan = 5; // Span all columns
        globalActionCell.className = 'text-end'; // Align buttons to the right

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
        const thead = table.createTHead(); // A new thead for column headers for clarity
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

            // Metric Name
            const nameCell = row.insertCell();
            nameCell.textContent = metric.displayName;

            // Current Value
            const currentValueCell = row.insertCell();
            const currentValue = currentWeatherData[metric.currentValueKey];
            currentValueCell.textContent = (currentValue !== undefined && currentValue !== null) ? `${currentValue}${metric.unit}` : 'N/A';

            // Thresholds
            const thresholdCell = row.insertCell();
            const thresholdValue = thresholds[metric.thresholdKey];
            thresholdCell.innerHTML = (thresholdValue !== undefined && thresholdValue !== null) ? `${metric.comparison}${thresholdValue}${metric.unit}` : 'N/A';


            // Set Value (initially blank)
            const setValueCell = row.insertCell();
            setValueCell.id = `set-value-${metric.id}`;
            setValueCell.textContent = ''; // Blank as per requirement

            // Action
            const actionCell = row.insertCell();
            const setButton = document.createElement('button');
            setButton.id = `set-to-threshold-${metric.id}-btn`;
            setButton.className = 'btn btn-sm btn-outline-secondary';
            setButton.textContent = 'Set to Threshold';
            setButton.setAttribute('data-metric', metric.id);
            actionCell.appendChild(setButton);
        });

        tableContainer.appendChild(table);

    } catch (error) {
        console.error('Error initializing test conditions table:', error);
        tableContainer.innerHTML = `<div class="alert alert-danger">Failed to load test conditions table: ${error.message}</div>`;
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

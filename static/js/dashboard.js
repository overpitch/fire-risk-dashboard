// Configure client-side settings
const settings = {
    refreshInterval: 300000, // 5 minutes
    maxRetries: 3,
    retryDelay: 2000, // 2 seconds
    waitForFreshTimeout: 30000 // 30 seconds (increased to match server-side timeout)
};

async function fetchWithTimeout(url, options, timeout) {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeout);

    try {
        const response = await fetch(url, {
            ...options,
            signal: controller.signal
        });
        clearTimeout(id);
        return response;
    } catch (error) {
        clearTimeout(id);
        throw error;
    }
}

async function fetchFireRisk(showSpinner = false, waitForFresh = false) {
    // Show loading state if requested (for manual refresh)
    if (showSpinner) {
        document.getElementById('refresh-btn').innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Refreshing...';
        document.getElementById('refresh-btn').disabled = true;
    }

    let retries = 0;
    let success = false;
    let data;

    while (!success && retries < settings.maxRetries) {
        try {
            // Add wait_for_fresh parameter if specified
            const apiUrl = waitForFresh ?
                '/fire-risk?wait_for_fresh=true' :
                '/fire-risk';

            // Use timeout to prevent indefinite waiting
            const timeout = waitForFresh ?
                settings.waitForFreshTimeout :
                10000; // 10 seconds for normal requests

            console.log(`Fetching from ${apiUrl} with timeout ${timeout}ms, waitForFresh=${waitForFresh}`);
            const fetchStartTime = new Date().getTime();
            
            try {
                const response = await fetchWithTimeout(apiUrl, {}, timeout);
                const fetchEndTime = new Date().getTime();
                console.log(`Fetch completed in ${fetchEndTime - fetchStartTime}ms with status: ${response.status}`);

                if (!response.ok) {
                    console.error(`HTTP error ${response.status}: ${response.statusText}`);
                    throw new Error(`HTTP error ${response.status}`);
                }

                data = await response.json();
                
                // Enhanced debugging for refresh operation
                console.log(`RESPONSE DEBUG: Cache info:`, data.cache_info);
                console.log(`RESPONSE DEBUG: Is data from cache?`, data.cache_info?.using_cached_data);
                console.log(`RESPONSE DEBUG: Which fields are cached?`, data.weather?.cached_fields);
                
                // Set success as true FIRST since we got a valid response
                success = true;
                console.log(`✅ Refresh operation successful - data received`);
                
                // Enhanced logging to debug the refresh issue
                console.log(`DEBUG: Response data structure:`, JSON.stringify(data, null, 2));
                console.log(`DEBUG: cache_info.using_cached_data type:`, 
                           data.cache_info ? typeof data.cache_info.using_cached_data : 'undefined');
                console.log(`DEBUG: cache_info.using_cached_data value:`, 
                           data.cache_info ? data.cache_info.using_cached_data : 'undefined');
                
                // Only log a warning if we get cached data when we requested fresh data
                // Using non-strict equality check to handle both boolean and string "true"
                if (waitForFresh && data.cache_info && data.cache_info.using_cached_data == true) {
                    console.warn(`⚠️ Refresh operation returned cached data despite waitForFresh=true`);
                    // Just log a warning - DO NOT throw an error anymore
                }
                
                // Log wind gust data specifically to debug
                if (data && data.weather && data.weather.wind_gust) {
                    console.log(`Received wind_gust: ${data.weather.wind_gust}`);
                    
                    // Check if it's from cache
                    const isFromCache = data.cache_info && data.cache_info.using_cached_data && 
                                      data.weather.cached_fields && 
                                      data.weather.cached_fields.wind_gust === true;
                    console.log(`Wind gust data from cache: ${isFromCache}`);
                } else {
                    console.warn('No wind_gust data in response or it\'s null');
                }
            } catch (error) {
                const fetchEndTime = new Date().getTime();
                console.error(`Fetch failed after ${fetchEndTime - fetchStartTime}ms: ${error.message}`);
                throw error;
            }
        } catch (error) {
            retries++;
            console.error(`Error fetching data (attempt ${retries}/${settings.maxRetries}):`, error);

            if (retries < settings.maxRetries) {
                // Add exponential backoff for retries
                const delay = settings.retryDelay * Math.pow(2, retries - 1);
                await new Promise(resolve => setTimeout(resolve, delay));
            }
        }
    }

    if (!success) {
        // All retries failed
        if (showSpinner) {
            document.getElementById('refresh-btn').innerHTML = 'Refresh Failed - Try Again';
            document.getElementById('refresh-btn').disabled = false;
        }
        return false;
    }

    // Reset refresh button state first - this must happen regardless of anything else
    if (showSpinner) {
        try {
            document.getElementById('refresh-btn').innerHTML = 'Refresh Data';
            document.getElementById('refresh-btn').disabled = false;
        } catch (btnError) {
            console.error("Error resetting refresh button:", btnError);
            // Even if this fails, we continue to try updating the UI
        }
    }
    
    try {
        // Then update the UI with the fetched data
        const riskDiv = document.getElementById('fire-risk');
        const weatherDetails = document.getElementById('weather-details');
        const timestampDiv = document.getElementById('timestamp');
        const cacheInfoDiv = document.getElementById('cache-info');
        const dataStatusBtn = document.getElementById('data-status-btn'); // New button
        const dataStatusModalBody = document.getElementById('dataStatusModalBody'); // Modal body

        console.log("Updating UI with fetched data - risk level:", data.risk);
        
        // Update fire risk text (simplified)
        riskDiv.innerText = `Fire Risk: ${data.risk} - ${data.explanation}`;

        // Update cache information
        if (data.cache_info) {
            // Parse the ISO string with timezone info
            const lastUpdated = new Date(data.cache_info.last_updated);
            const isFresh = data.cache_info.is_fresh;
            const refreshInProgress = data.cache_info.refresh_in_progress;
            // const usingCachedData = data.cache_info.using_cached_data; // No longer needed here

            // Check if any data is older than 1 hour (stale)
            const hasStaleData = () => {
                if (!data.weather.cached_fields || !data.weather.cached_fields.timestamp) {
                    return false; // No cached data
                }

                const now = new Date();
                const ONE_HOUR_MS = 60 * 60 * 1000;

                // Check each timestamp field
                for (const field in data.weather.cached_fields.timestamp) {
                    if (data.weather.cached_fields.timestamp[field]) {
                        const dataTime = new Date(data.weather.cached_fields.timestamp[field]);
                        const ageMs = now - dataTime;

                        if (ageMs >= ONE_HOUR_MS) {
                            return true; // Found stale data
                        }
                    }
                }

                return false; // No stale data found
            };

            // Update data status button based on staleness (over 1 hour old)
            const dataIsStale = hasStaleData();

            if (!dataIsStale) {
                dataStatusBtn.textContent = 'Fresh Data';
                dataStatusBtn.classList.remove('btn-warning');
                dataStatusBtn.classList.add('btn-success');
            } else {
                dataStatusBtn.textContent = 'Older Data'; // Changed from "Stale Data" to "Older Data"
                dataStatusBtn.classList.remove('btn-success');
                dataStatusBtn.classList.add('btn-warning');
            }
            dataStatusBtn.disabled = false; // Enable button once data loads

            // Update Modal Content based on backend data
            let modalHTML = '';
            if (data.modal_content) {
                if (data.modal_content.note) {
                    modalHTML += `<div class="alert alert-info p-2 small"><strong>NOTE:</strong> ${data.modal_content.note}</div>`;
                }
                if (data.modal_content.warning_title && data.modal_content.warning_issues && data.modal_content.warning_issues.length > 0) {
                    modalHTML += `<div class="alert alert-warning p-2 small">
                        <strong>${data.modal_content.warning_title}</strong><br>
                        <ul class="mb-0">
                            ${data.modal_content.warning_issues.map(issue => `<li>${issue}</li>`).join('')}
                        </ul>
                    </div>`;
                }
            }
            if (!modalHTML) {
                modalHTML = '<p>Data is current and no quality issues detected.</p>'; // Default message
            }
            dataStatusModalBody.innerHTML = modalHTML;


            // Update Cache Info Div (Timestamp only)
            // Extract timezone abbreviation from timestamp
            // This will properly display the timezone from the server
            const timeZoneAbbr = (() => {
                // The timestamp from the server now includes timezone info
                // We can get the timezone offset directly from the parsed date
                const offset = lastUpdated.getTimezoneOffset();
                const offsetHours = Math.abs(Math.floor(offset / 60));

                // Check if we're in DST based on timezone offset
                const jan = new Date(lastUpdated.getFullYear(), 0, 1).getTimezoneOffset();
                const jul = new Date(lastUpdated.getFullYear(), 6, 1).getTimezoneOffset();
                const isDST = offset < Math.max(jan, jul);

                // For Pacific Time
                if (offset >= 420 && offset <= 480) { // -7 or -8 hours
                    return isDST ? 'PDT' : 'PST';
                }
                return `GMT${offset <= 0 ? '+' : '-'}${offsetHours}`;
            })();

            let statusText = '';
            if (refreshInProgress) {
                statusText += ' (refresh in progress...)'; // Keep refresh status
            } else {
                statusText = ''; // Clear status text if not refreshing
            }

            // Store the server timestamp for consistent display throughout the page
            window.serverTimestamp = {
                date: lastUpdated,
                formatted: `${lastUpdated.toLocaleDateString()} at ${lastUpdated.toLocaleTimeString()} ${timeZoneAbbr}`,
                timeOnly: `${lastUpdated.toLocaleTimeString()} ${timeZoneAbbr}`
            };

            cacheInfoDiv.innerHTML = `
                <span class="cache-info">
                   Last updated: ${window.serverTimestamp.timeOnly}${statusText}
                </span>`;
        } else {
            cacheInfoDiv.innerHTML = `<span class="cache-info">Last updated: Unavailable</span>`; // Fallback
        }

        // Set appropriate background color based on risk level
        const riskLevel = data.risk;
        let bgClass = 'bg-secondary';  // Default for unknown/error risk
        let customStyle = '';

        if (riskLevel === 'Red') {
            bgClass = 'text-white'; // Text color for Red risk
            customStyle = 'background-color: #FF0000;'; // Red hex color
        } else if (riskLevel === 'Orange') {
            bgClass = 'text-dark'; // Text color for Orange risk
            customStyle = 'background-color: #FFA500;'; // Orange hex color
        }
        // Always set background color based on risk level now
        riskDiv.className = `alert ${bgClass} p-3`;
        riskDiv.style = customStyle; // Apply custom hex color

        // Update weather details
        // Convert temperature from Celsius to Fahrenheit using the formula F = (C * 9/5) + 32
        // Round all measurements to the nearest whole number
        const tempCelsius = data.weather.air_temp;
        // Check if we have cached values for any missing fields
        const isCachedTemp = data.weather.cached_fields && data.weather.cached_fields.temperature;
        const isCachedSoilMoisture = data.weather.cached_fields && data.weather.cached_fields.soil_moisture;

        // Use cached values if available, otherwise show unavailable
        // Format age for cached data
        const formatAge = (timestamp) => {
            if (!timestamp) return "";

            const now = new Date();
            const dataTime = new Date(timestamp);
            const ageMs = now - dataTime;

            // Convert to minutes
            const ageMinutes = Math.round(ageMs / (1000 * 60));

            if (ageMinutes < 60) {
                return `${ageMinutes} minute${ageMinutes !== 1 ? 's' : ''} old`;
            } else if (ageMinutes < 24 * 60) {
                const hours = Math.round(ageMinutes / 60);
                return `${hours} hour${hours !== 1 ? 's' : ''} old`;
            } else if (ageMinutes < 7 * 24 * 60) {
                const days = Math.round(ageMinutes / (60 * 24));
                return `${days} day${days !== 1 ? 's' : ''} old`;
            } else {
                const weeks = Math.round(ageMinutes / (60 * 24 * 7));
                return `${weeks} week${weeks !== 1 ? 's' : ''} old`;
            }
        };

        // Add age info as a second line for cached data
        const getTempDisplay = () => {
            // Check if we're in test mode or using cached data
            const usingCachedData = data.cache_info && data.cache_info.using_cached_data;

            // If we're in test mode and have a timestamp, show age indicator even if primary data exists
            if (isCachedTemp && data.weather.cached_fields.timestamp && usingCachedData) {
                const tempValue = Math.round((tempCelsius || data.weather.cached_fields.temperature) * 9 / 5) + 32 + '°F';
                const ageText = formatAge(data.weather.cached_fields.timestamp.temperature);
                return `${tempValue}<br><span class="data-age">(${ageText})</span>`;
            } else if (tempCelsius) {
                return Math.round((tempCelsius * 9 / 5) + 32) + '°F';
            } else if (isCachedTemp && data.weather.cached_fields.timestamp) {
                const tempValue = Math.round((data.weather.cached_fields.temperature) * 9 / 5) + 32 + '°F';
                const ageText = formatAge(data.weather.cached_fields.timestamp.temperature);
                return `${tempValue}<br><span class="data-age">(${ageText})</span>`;
            } else {
                // With our enhanced caching system, this should never happen
                // But if it does, display a loading message instead of "unavailable"
                return '<span class="text-secondary">Loading data...</span>';
            }
        };

        const getSoilMoistureDisplay = () => {
            // Check if we're in test mode or using cached data
            const usingCachedData = data.cache_info && data.cache_info.using_cached_data;

            // If we're in test mode and have a timestamp, show age indicator even if primary data exists
            if (isCachedSoilMoisture && data.weather.cached_fields.timestamp && usingCachedData) {
                const moistureValue = Math.round(data.weather.soil_moisture_15cm || data.weather.cached_fields.soil_moisture) + '%';
                const ageText = formatAge(data.weather.cached_fields.timestamp.soil_moisture);
                return `${moistureValue}<br><span class="data-age">(${ageText})</span>`;
            } else if (data.weather.soil_moisture_15cm) {
                return Math.round(data.weather.soil_moisture_15cm) + '%';
            } else if (isCachedSoilMoisture && data.weather.cached_fields.timestamp) {
                const moistureValue = Math.round(data.weather.cached_fields.soil_moisture) + '%';
                const ageText = formatAge(data.weather.cached_fields.timestamp.soil_moisture);
                return `${moistureValue}<br><span class="data-age">(${ageText})</span>`;
            } else {
                // With our enhanced caching system, this should never happen
                // But if it does, display a loading message instead of "unavailable"
                return '<span class="text-secondary">Loading data...</span>';
            }
        };

        const tempFahrenheit = getTempDisplay();
        const soilMoisture = getSoilMoistureDisplay();
        const weatherStation = data.weather.data_sources.weather_station;
        const soilStation = data.weather.data_sources.soil_moisture_station;

        // Check for data issues
        const dataStatus = data.weather.data_status;
        const hasIssues = dataStatus && dataStatus.issues && dataStatus.issues.length > 0;
        // Build the weather details HTML (Removed NOTE and Warning - now in modal)
        let detailsHTML = `<h5>Current Weather Conditions:</h5>`;

        // Handle potentially missing data with fallbacks - round all values to nearest whole number
        // Check if we have cached values for any missing fields
        const isCachedHumidity = data.weather.cached_fields && data.weather.cached_fields.humidity;
        const isCachedWindSpeed = data.weather.cached_fields && data.weather.cached_fields.wind_speed;
        const isCachedWindGust = data.weather.cached_fields && data.weather.cached_fields.wind_gust;

        // Create display functions for remaining weather metrics with age-based formatting
        const getHumidityDisplay = () => {
            // Check if we're in test mode or using cached data
            const usingCachedData = data.cache_info && data.cache_info.using_cached_data;

            // If we're in test mode and have a timestamp, show age indicator even if primary data exists
            if (isCachedHumidity && data.weather.cached_fields.timestamp && usingCachedData) {
                const humidValue = Math.round(data.weather.relative_humidity || data.weather.cached_fields.humidity) + '%';
                const ageText = formatAge(data.weather.cached_fields.timestamp.humidity);
                return `${humidValue}<br><span class="data-age">(${ageText})</span>`;
            } else if (data.weather.relative_humidity) {
                return Math.round(data.weather.relative_humidity) + '%';
            } else if (isCachedHumidity && data.weather.cached_fields.timestamp) {
                const humidValue = Math.round(data.weather.cached_fields.humidity) + '%';
                const ageText = formatAge(data.weather.cached_fields.timestamp.humidity);
                return `${humidValue}<br><span class="data-age">(${ageText})</span>`;
            } else {
                // With our enhanced caching system, this should never happen
                // But if it does, display a loading message instead of "unavailable"
                return '<span class="text-secondary">Loading data...</span>';
            }
        };

        const getWindSpeedDisplay = () => {
            // Check if we're in test mode or using cached data
            const usingCachedData = data.cache_info && data.cache_info.using_cached_data;

            // If we're in test mode and have a timestamp, show age indicator even if primary data exists
            if (isCachedWindSpeed && data.weather.cached_fields.timestamp && usingCachedData) {
                // Convert to mph if the value is in m/s (API returns m/s but we display mph)
                const rawSpeed = data.weather.wind_speed || data.weather.cached_fields.wind_speed;
                // Check if rawSpeed is already in mph or needs to be converted from m/s
                // Synoptic API returns m/s, but our cache might store in either format
                // We can assume values under 30 are likely m/s and should be converted
                const speedValue = rawSpeed < 30 ? Math.round(rawSpeed * 2.237) + ' mph' : Math.round(rawSpeed) + ' mph';
                const ageText = formatAge(data.weather.cached_fields.timestamp.wind_speed);
                return `${speedValue}<br><span class="data-age">(${ageText})</span>`;
            } else if (data.weather.wind_speed !== null && data.weather.wind_speed !== undefined) {
                // Convert from m/s to mph - Synoptic API returns wind speed in m/s
                return Math.round(data.weather.wind_speed * 2.237) + ' mph';
            } else if (isCachedWindSpeed && data.weather.cached_fields.timestamp) {
                // Convert to mph if the value is in m/s (API returns m/s but we display mph)
                const rawSpeed = data.weather.cached_fields.wind_speed;
                // Check if rawSpeed is already in mph or needs to be converted from m/s
                const speedValue = rawSpeed < 30 ? Math.round(rawSpeed * 2.237) + ' mph' : Math.round(rawSpeed) + ' mph';
                const ageText = formatAge(data.weather.cached_fields.timestamp.wind_speed);
                return `${speedValue}<br><span class="data-age">(${ageText})</span>`;
            } else {
                // With our enhanced caching system, this should never happen
                // But if it does, display a loading message instead of "unavailable"
                return '<span class="text-secondary">Loading data...</span>';
            }
        };

        const getWindGustDisplay = () => {
            // Check if we're in test mode or using cached data
            const usingCachedData = data.cache_info && data.cache_info.using_cached_data;

            // If we're in test mode and have a timestamp, show age indicator even if primary data exists
            if (isCachedWindGust && data.weather.cached_fields.timestamp && usingCachedData) {
                // Convert to mph if the value is in m/s (API returns m/s but we display mph)
                const rawGust = data.weather.wind_gust || data.weather.cached_fields.wind_gust;
                // Check if rawGust is already in mph or needs to be converted from m/s
                const gustValue = rawGust < 30 ? Math.round(rawGust * 2.237) + ' mph' : Math.round(rawGust) + ' mph';
                const ageText = formatAge(data.weather.cached_fields.timestamp.wind_gust);
                return `${gustValue}<br><span class="data-age">(${ageText})</span>`;
            } else if (data.weather.wind_gust !== null && data.weather.wind_gust !== undefined) {
                // Convert from m/s to mph - Synoptic API returns wind gust in m/s
                return Math.round(data.weather.wind_gust * 2.237) + ' mph';
            } else if (isCachedWindGust && data.weather.cached_fields.timestamp) {
                // Convert to mph if the value is in m/s (API returns m/s but we display mph)
                const rawGust = data.weather.cached_fields.wind_gust;
                // Check if rawGust is already in mph or needs to be converted from m/s
                const gustValue = rawGust < 30 ? Math.round(rawGust * 2.237) + ' mph' : Math.round(rawGust) + ' mph';
                const ageText = formatAge(data.weather.cached_fields.timestamp.wind_gust);
                return `${gustValue}<br><span class="data-age">(${ageText})</span>`;
            } else {
                // With our enhanced caching system, this should never happen
                // But if it does, display a loading message instead of "unavailable"
                return '<span class="text-secondary">Loading data...</span>';
            }
        };

        // Get display values for all metrics
        const humidity = getHumidityDisplay();
        const windSpeed = getWindSpeedDisplay();
        const windGust = getWindGustDisplay();
        const windGustStation = data.weather.data_sources.wind_gust_station;

        // Get threshold values from API response or use defaults if not available
        const THRESH_TEMP = data.thresholds ? data.thresholds.temp : 75; // Temperature threshold in Fahrenheit
        const THRESH_HUMID = data.thresholds ? data.thresholds.humid : 15; // Humidity threshold in percent (below this is risky)
        const THRESH_WIND = data.thresholds ? data.thresholds.wind : 15;  // Wind speed threshold in mph
        const THRESH_GUSTS = data.thresholds ? data.thresholds.gusts : 20; // Wind gust threshold in mph
        const THRESH_SOIL_MOIST = data.thresholds ? data.thresholds.soil_moist : 10; // Soil moisture threshold in percent (below this is risky)

        // Check if values exceed thresholds for color formatting - use rounded values
        const tempValue = tempCelsius ? Math.round((tempCelsius * 9 / 5) + 32) : null;
        const tempExceeds = tempValue !== null && tempValue > THRESH_TEMP;

        const humidValue = data.weather.relative_humidity ? Math.round(data.weather.relative_humidity) : null;
        const humidExceeds = humidValue !== null && humidValue < THRESH_HUMID;

        const windValue = data.weather.wind_speed ? Math.round(data.weather.wind_speed * 2.237) : null; // Convert to mph
        const windExceeds = windValue !== null && windValue > THRESH_WIND;

        const gustValue = data.weather.wind_gust ? Math.round(data.weather.wind_gust * 2.237) : null; // Convert to mph
        const gustExceeds = gustValue !== null && gustValue > THRESH_GUSTS;

        const soilValue = data.weather.soil_moisture_15cm ? Math.round(data.weather.soil_moisture_15cm) : null;
        const soilExceeds = soilValue !== null && soilValue < THRESH_SOIL_MOIST;

        // Removed weatherContainerClass - no special styling needed here now

        // Create a style for the threshold display (used temporarily during revert then replaced)
        const thresholdStyle = "display: inline-block; margin-left: 10px; font-size: 0.85rem; color: #6c757d; border-left: 1px solid #ddd; padding-left: 10px;";

        detailsHTML += `
            <div>
                <ul>
                    <li style="color: ${tempExceeds ? 'red' : 'black'}">
                        <span class="weather-value-label">
                            <span style="color: ${tempExceeds ? 'red' : 'black'}">Temperature: ${tempFahrenheit}</span>
                        </span>
                        <span class="threshold-info">Thresholds: >${THRESH_TEMP}°F</span>
                        <span class="simple-tooltip">
                            <span class="info-icon">ⓘ</span>
                            <span class="tooltip-text">Sierra City<br>From: Synoptic Data</span>
                        </span>
                    </li>
                    <li style="color: ${humidExceeds ? 'red' : 'black'}">
                        <span class="weather-value-label">
                            <span style="color: ${humidExceeds ? 'red' : 'black'}">Humidity: ${humidity}</span>
                        </span>
                        <span class="threshold-info"><${THRESH_HUMID}%</span>
                        <span class="simple-tooltip">
                            <span class="info-icon">ⓘ</span>
                            <span class="tooltip-text">Sierra City<br>From: Synoptic Data</span>
                        </span>
                    </li>
                    <li style="color: ${windExceeds ? 'red' : 'black'}">
                        <span class="weather-value-label">
                            <span style="color: ${windExceeds ? 'red' : 'black'}">Average Winds: ${windSpeed}</span>
                        </span>
                        <span class="threshold-info">>${THRESH_WIND} mph</span>
                        <span class="simple-tooltip">
                            <span class="info-icon">ⓘ</span>
                            <span class="tooltip-text">PG&E Sand Shed<br>From: Synoptic Data</span>
                        </span>
                    </li>
                    <li style="color: ${gustExceeds ? 'red' : 'black'}">
                        <span class="weather-value-label">
                            <span style="color: ${gustExceeds ? 'red' : 'black'}">Wind Gust: ${windGust}</span>
                        </span>
                        <span class="threshold-info">>${THRESH_GUSTS} mph</span>
                        <span class="simple-tooltip">
                            <span class="info-icon">ⓘ</span>
                            <span class="tooltip-text">PG&E Sand Shed<br>From: Synoptic Data</span>
                        </span>
                    </li>
                    <li style="color: ${soilExceeds ? 'red' : 'black'}">
                        <span class="weather-value-label">
                            <span style="color: ${soilExceeds ? 'red' : 'black'}">Soil Moisture (15cm depth): ${soilMoisture}</span>
                        </span>
                        <span class="threshold-info"><${THRESH_SOIL_MOIST}%</span>
                        <span class="simple-tooltip">
                            <span class="info-icon">ⓘ</span>
                            <span class="tooltip-text">Downieville<br>From: Synoptic Data</span>
                        </span>
                    </li>
                </ul>
            </div>`;

        weatherDetails.innerHTML = detailsHTML;

        // Update timestamp and re-enable refresh button if it was used
        // Instead of creating a new timestamp here, use the server timestamp we saved above
        timestampDiv.innerText = `Last updated: ${window.serverTimestamp.formatted}`;

        if (showSpinner) {
            document.getElementById('refresh-btn').innerHTML = 'Refresh Data';
            document.getElementById('refresh-btn').disabled = false;
        }

        // Update the wind gust tooltip with station data
        if (data.weather.wind_gust_stations) {
            const tooltipContent = buildWindGustTooltip(data.weather.wind_gust_stations);
            const windGustTooltip = document.querySelector('.wind-gust-info');
            if (windGustTooltip) {
                // Update the tooltip content
                const tooltip = bootstrap.Tooltip.getInstance(windGustTooltip);
                if (tooltip) {
                    tooltip.dispose(); // Remove existing tooltip
                }
                windGustTooltip.setAttribute('title', tooltipContent);
                // Reinitialize the tooltip with standard styling to match other tooltips
                new bootstrap.Tooltip(windGustTooltip, {
                    html: true
                });
            }
        }

        return true; // Signal success

    } catch (error) {
        console.error("Error fetching fire risk data:", error);
        if (showSpinner) {
            document.getElementById('refresh-btn').innerHTML = 'Refresh Failed - Try Again';
            document.getElementById('refresh-btn').disabled = false;
        }
        return false;
    }
}

// Build tooltip content for wind gust stations
function buildWindGustTooltip(stationsData) {
    // Simplified to match other tooltips - removed station identifier line
    return "PG&E Sand Shed<br>From: Synoptic Data";
}

// Completely custom tooltip implementation
function initializeTooltips() {
    console.log("Setting up custom tooltip implementation");
    
    try {
        // First completely remove Bootstrap tooltips
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.forEach(function (tooltipTriggerEl) {
            try {
                const tooltip = bootstrap.Tooltip.getInstance(tooltipTriggerEl);
                if (tooltip) {
                    tooltip.dispose();
                }
            } catch (e) {
                console.error("Error disposing tooltip:", e);
            }
            
            // Remove Bootstrap tooltip attributes
            tooltipTriggerEl.removeAttribute('data-bs-toggle');
            
            // Get the title content
            const title = tooltipTriggerEl.getAttribute('title') || 
                          tooltipTriggerEl.getAttribute('data-bs-original-title') || 
                          "Station Information";
            
            // Store title for later use but remove it to prevent default browser tooltip
            tooltipTriggerEl.dataset.tooltipContent = title;
            tooltipTriggerEl.removeAttribute('title');
            tooltipTriggerEl.removeAttribute('data-bs-original-title');
        });
        
        // Remove any existing custom tooltips
        const existingTooltips = document.querySelectorAll('.custom-tooltip');
        existingTooltips.forEach(tooltip => tooltip.remove());
        
        // Create a custom tooltip element and add to the DOM
        const customTooltip = document.createElement('div');
        customTooltip.className = 'custom-tooltip';
        customTooltip.style.cssText = `
            position: absolute;
            z-index: 9999;
            background-color: rgba(0, 0, 0, 0.9);
            color: white;
            padding: 12px 16px;
            border-radius: 6px;
            font-size: 14px;
            max-width: 350px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4);
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.2s;
            font-weight: normal;
            line-height: 1.6;
            text-align: left;
            display: none;
        `;
        document.body.appendChild(customTooltip);
        
        // Function to show tooltip
        function showTooltip(event) {
            const tooltipContent = event.target.dataset.tooltipContent;
            if (!tooltipContent) return;
            
            // Position tooltip near the cursor
            const x = event.clientX + 15;
            const y = event.clientY - 20;
            
            // Set content and position
            customTooltip.innerHTML = tooltipContent;
            customTooltip.style.left = `${x}px`;
            customTooltip.style.top = `${y}px`;
            
            // Show tooltip
            customTooltip.style.display = 'block';
            setTimeout(() => {
                customTooltip.style.opacity = '1';
            }, 10);
        }
        
        // Function to hide tooltip
        function hideTooltip() {
            customTooltip.style.opacity = '0';
            setTimeout(() => {
                customTooltip.style.display = 'none';
            }, 200);
        }
        
        // Function to update tooltip position on mouse move
        function moveTooltip(event) {
            const x = event.clientX + 15;
            const y = event.clientY - 20;
            customTooltip.style.left = `${x}px`;
            customTooltip.style.top = `${y}px`;
        }
        
        // Add event listeners to info icons
        document.querySelectorAll('.info-icon').forEach(icon => {
            icon.style.cursor = 'pointer';
            
            // Use mouseenter instead of mouseover for better behavior
            icon.addEventListener('mouseenter', showTooltip);
            icon.addEventListener('mouseleave', hideTooltip);
            icon.addEventListener('mousemove', moveTooltip);
            
            // Also handle focus/blur for accessibility
            icon.addEventListener('focus', showTooltip);
            icon.addEventListener('blur', hideTooltip);
        });
        
        console.log("Custom tooltip implementation complete");
    } catch (e) {
        console.error("Critical error in custom tooltip implementation:", e);
    }
}

// Reset refresh button regardless of success/failure
function resetRefreshButton(showFailure = false) {
    try {
        const refreshBtn = document.getElementById('refresh-btn');
        if (refreshBtn) {
            if (showFailure) {
                refreshBtn.innerHTML = 'Refresh Failed - Try Again';
            } else {
                refreshBtn.innerHTML = 'Refresh Data';
            }
            refreshBtn.disabled = false;
        }
    } catch (error) {
        console.error("Critical error resetting refresh button:", error);
        // At this point, there's nothing more we can do
    }
}

// Completely separate manual refresh implementation to avoid any issues with the main fetchFireRisk
async function manualRefresh() {
    try {
        // Set button to loading state
        const refreshBtn = document.getElementById('refresh-btn');
        refreshBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Refreshing...';
        refreshBtn.disabled = true;
        
        console.log("Manual refresh initiated - direct implementation");
        
        try {
            // Simple fetch with minimal error handling
            const response = await fetch('/fire-risk?wait_for_fresh=true', {
                method: 'GET',
                headers: { 'Accept': 'application/json' },
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error ${response.status}`);
            }
            
            const data = await response.json();
            console.log("Manual refresh successful - received data");
            
            // Reset button first
            refreshBtn.innerHTML = 'Refresh Data';
            refreshBtn.disabled = false;
            
            // Update the page by reloading it - simplest and most reliable approach
            window.location.reload();
            
            return true;
        } catch (fetchError) {
            console.error("Error during manual refresh fetch:", fetchError);
            refreshBtn.innerHTML = 'Refresh Failed - Try Again';
            refreshBtn.disabled = false;
            return false;
        }
    } catch (error) {
        console.error("Critical error in manualRefresh:", error);
        try {
            document.getElementById('refresh-btn').innerHTML = 'Refresh Failed - Try Again';
            document.getElementById('refresh-btn').disabled = false;
        } catch (e) {
            // Nothing more we can do if this fails
        }
        return false;
    }
}

// Test Mode Toggle Functionality
async function toggleTestMode(enable) {
    // Update the toggle color immediately
    const testModeToggle = document.getElementById('testModeToggle');
    if (enable) {
        // Switch to red for test mode
        testModeToggle.classList.remove('normal-mode');
        testModeToggle.classList.add('test-mode');
    } else {
        // Switch to green for normal mode
        testModeToggle.classList.remove('test-mode');
        testModeToggle.classList.add('normal-mode');
    }

    try {
        const response = await fetch(`/toggle-test-mode?enable=${enable}`, {
            method: 'GET'
        });

        const data = await response.json();

        if (response.ok) {
            // Log success message based on mode
            if (enable) {
                console.log('Test mode enabled. Using cached data.');
            } else {
                console.log('Test mode disabled. Returned to normal operation.');
            }

            // Refresh the data display to show the changes
            fetchFireRisk(true, true).then(success => {
                if (success !== false) {
                    initializeTooltips();
                }
            });

            // Don't save test mode state to localStorage anymore
            // We want test mode to always start disabled by default

            return true;
        } else {
            console.error(`Error toggling test mode: ${data.message}`);
            alert(`Error: ${data.message}`);

            // Reset the toggle to its previous state without triggering the change event
            const testModeToggle = document.getElementById('testModeToggle');
            testModeToggle.checked = !enable;

            return false;
        }
    } catch (error) {
        console.error('Error toggling test mode:', error);
        alert('Error toggling test mode. See console for details.');

        // Reset the toggle to its previous state without triggering the change event
        const testModeToggle = document.getElementById('testModeToggle');
        testModeToggle.checked = !enable;

        return false;
    }
}

// Auto-refresh functionality
function setupRefresh() {
    // Test mode toggle has been moved to admin page
    // No need to initialize it here anymore
    
    // Clear any previously saved test mode state from localStorage
    localStorage.removeItem('testModeEnabled');

    // Initial load without waiting for fresh data
    fetchFireRisk().then(success => {
        if (success !== false) {
            initializeTooltips();
        }
    });

    // Setup auto-refresh
    setInterval(() => {
        // Don't wait for fresh data on auto-refresh, to prevent hanging the UI
        fetchFireRisk(false, false).then(success => {
            if (success !== false) {
                initializeTooltips();
            }
        });
    }, settings.refreshInterval);
}

window.onload = setupRefresh;

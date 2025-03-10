<!DOCTYPE html>
<html lang='en'>
<head>
    <meta charset='UTF-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>Fire Risk Dashboard</title>
    <link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css' rel='stylesheet'>
    <style>
        .loading-spinner {
            border: 4px solid rgba(0, 0, 0, 0.1);
            width: 36px;
            height: 36px;
            border-radius: 50%;
            border-left-color: #09f;
            animation: spin 1s linear infinite;
            display: inline-block;
            margin-right: 10px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .weather-details {
            margin-top: 20px;
            padding: 15px;
            background-color: rgba(255, 255, 255, 0.1);
            border-radius: 5px;
        }
    </style>
</head>
<body class='container mt-5'>
    <div class="row">
        <div class="col-md-8 offset-md-2">
            <h1 class='mb-3'>Sierra City Fire Risk Dashboard</h1>
            <div id='status-message' class='alert alert-info'>Loading data...</div>
            <div id='fire-risk' class='p-4 text-white mb-3 rounded' style='display: none;'></div>
            <div id='weather-details' class='weather-details text-white' style='display: none;'></div>
            <div class="d-flex justify-content-between align-items-center mt-4">
                <small class="text-muted">Last updated: <span id="last-updated">Never</span></small>
                <button id="refresh-btn" class="btn btn-outline-secondary btn-sm">Refresh Now</button>
            </div>
        </div>
    </div>
    <script>
        const REFRESH_INTERVAL = 300000; // 5 minutes in milliseconds
        let refreshTimer;
        const statusMessage = document.getElementById('status-message');
        const riskDiv = document.getElementById('fire-risk');
        const weatherDetails = document.getElementById('weather-details');
        const lastUpdatedSpan = document.getElementById('last-updated');
        const refreshBtn = document.getElementById('refresh-btn');
        function formatDateTime(date) {
            return date.toLocaleTimeString() + ' ' + date.toLocaleDateString();
        }
        function showError(message) {
            statusMessage.className = 'alert alert-danger';
            statusMessage.textContent = `Error: ${message}`;
            statusMessage.style.display = 'block';
            riskDiv.style.display = 'none';
            weatherDetails.style.display = 'none';
        }
        function showLoading() {
            statusMessage.className = 'alert alert-info';
            statusMessage.innerHTML = '<div class="loading-spinner"></div> Fetching latest fire risk data...';
            statusMessage.style.display = 'block';
        }
        function updateUI(data) {
            riskDiv.textContent = `Fire Risk: ${data.risk} - ${data.explanation}`;
            const bgClass = data.risk === 'Red' ? 'bg-danger' :
                            data.risk === 'Yellow' ? 'bg-warning text-dark' :
                            data.risk === 'Green' ? 'bg-success' :
                            'bg-secondary';
            riskDiv.className = `p-4 text-white mb-3 rounded ${bgClass}`;
            if (data.risk === 'Yellow') riskDiv.classList.replace('text-white', 'text-dark');
            const weather = data.weather;
            weatherDetails.innerHTML = `
                <h5>Current Weather Conditions:</h5>
                <ul>
                    <li>Temperature: ${weather.air_temp}°F</li>
                    <li>Humidity: ${weather.relative_humidity}%</li>
                    <li>Wind Speed: ${weather.wind_speed} mph</li>
                </ul>
            `;
            statusMessage.style.display = 'none';
            riskDiv.style.display = 'block';
            weatherDetails.style.display = 'block';
            weatherDetails.className = `weather-details ${bgClass}`;
            if (data.risk === 'Yellow') weatherDetails.classList.replace('text-white', 'text-dark');
            lastUpdatedSpan.textContent = formatDateTime(new Date());
        }
        async function fetchFireRisk() {
            clearTimeout(refreshTimer);
            showLoading();
            try {
                const response = await fetch('/fire-risk');
                if (!response.ok) {
                    let errorText = `Server returned ${response.status}`;
                    try {
                        const errorData = await response.json();
                        if (errorData.detail) errorText += `: ${errorData.detail}`;
                    } catch (e) {}
                    throw new Error(errorText);
                }
                const data = await response.json();
                updateUI(data);
            } catch (error) {
                showError(error.message || 'Failed to fetch fire risk data');
                console.error('Fetch error:', error);
            } finally {
                refreshTimer = setTimeout(fetchFireRisk, REFRESH_INTERVAL);
            }
        }
        fetchFireRisk();
        refreshBtn.addEventListener('click', fetchFireRisk);
    </script>
</body>
</html>

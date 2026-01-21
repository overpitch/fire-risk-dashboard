# External Integrations

**Analysis Date:** 2026-01-21

## APIs & External Services

**Weather Data:**
- Synoptic Data API - Primary source for real-time weather conditions
  - SDK/Client: `requests` library (HTTP calls)
  - Auth: API key authentication via `SYNOPTICDATA_API_KEY` environment variable
  - Endpoint: `https://api.synopticdata.com/v2`
  - Implementation: `api_clients.py` - functions `get_api_token()`, `get_weather_data()`, `get_synoptic_data()`
  - Station IDs monitored:
    - `C3DLA` - Soil moisture data
    - `SEYC1` - Temperature and humidity
    - `629PG` - Wind speed and gust data (PG&E Sand Shed)
  - Authentication flow: Permanent API key → temporary token exchange → data requests with token
  - Retry logic: Exponential backoff, max 4 retries for authentication failures
  - Fallback mechanism: Cached JSON data at `data/synoptic_fallback_data.json` used on API failures

**Legacy Weather Integration (Deprecated):**
- Weather Underground API - No longer actively used
  - Reason: Replaced by Synoptic API
  - References remain in config but code paths are commented out

## Data Storage

**Databases:**
- SQLite3 (Local file-based)
  - Connection: `subscribers.db` (embedded database file)
  - Location: Root directory of application
  - Client: Python built-in `sqlite3` module
  - Usage: Subscriber email list management

**File Storage:**
- Local filesystem only
  - Static files: `static/` directory (HTML, CSS, JS, images)
  - Templates: `./templates/` directory (Jinja2 email templates)
  - Cache data: `data/synoptic_fallback_data.json`
  - No cloud storage (S3, Azure Blob, etc.) currently integrated

**Caching:**
- In-memory cache: Python `DataCache` class in `cache.py`
  - Stores: Temperature, humidity, wind speed, wind gust, soil moisture
  - Thread-safe with locks
  - Async event signaling for update completion
- Disk cache: JSON file at `data/weather_cache.json`
  - Persists weather data across application restarts
  - Fallback for API outages

## Authentication & Identity

**Auth Provider:**
- Custom implementation via session tokens
  - Session storage: In-memory dictionary `admin_sessions` in `admin_endpoints.py`
  - Token format: Session-based (cookie-based authentication)
  - No third-party identity provider (Auth0, Okta, etc.)
  - Admin endpoints protected by session token validation
  - Session validation happens in `admin_endpoints.py` route handlers

## Email Service

**Email Provider:**
- AWS SES (Simple Email Service)
  - SDK/Client: boto3 (`boto3.client('ses')`)
  - Auth: AWS credentials via environment variables
    - `AWS_REGION` (us-west-1)
    - `AWS_ACCESS_KEY_ID`
    - `AWS_SECRET_ACCESS_KEY`
  - Implementation: `email_service.py`
  - Sender email: `advisory@scfireweather.org` (verified SES sender)
  - Features:
    - Generic email sending: `send_email()`
    - Alert-specific: `send_orange_to_red_alert()` with Jinja2 template rendering
    - Bulk sending: `send_custom_email_to_subscribers()`
    - HTML and plain text support
    - Per-recipient error tracking

**Email Templates:**
- Jinja2 templating system
  - Template directory: `./templates/`
  - Email templates:
    - `orange_to_red_alert.html` - HTML alert template
    - `orange_to_red_alert.txt` - Plain text alert template
  - Fallback: Basic text email if template rendering fails
  - Weather data context: temperature, humidity, wind_speed, wind_gust, soil_moisture

## Monitoring & Observability

**Error Tracking:**
- None detected - No Sentry, Rollbar, or similar integration

**Logs:**
- Python logging module (standard library)
  - Configuration: `config.py` sets up logging at INFO level
  - Format: `"%(asctime)s - %(name)s - %(levelname)s - %(message)s"`
  - Emojis used in log messages for visual clarity (debug aid)
  - Debug logging controlled via `DEBUG_API_RESPONSES` environment variable
  - Captured by application stdout/stderr on Render platform

**Metrics:**
- None detected - No Prometheus, DataDog, or similar

## CI/CD & Deployment

**Hosting:**
- Render (PaaS)
  - Deployment: Continuous deployment on push to main branch
  - CORS origin: `https://fire-risk-dashboard.onrender.com`
  - Environment detection: `IS_PRODUCTION = os.getenv("RENDER") is not None`

**CI Pipeline:**
- GitHub Actions
  - Workflow file: `.github/workflows/tests.yml`
  - Trigger: On push to main and pull requests to main
  - Environment: Ubuntu latest
  - Python version: 3.11
  - Steps:
    1. Checkout code
    2. Set up Python 3.11
    3. Install dependencies from requirements-dev.txt
    4. Run pytest on tests/test_fire_risk_logic.py
  - No deployment automation in workflow (likely manual or Render's auto-deploy on git push)

## Environment Configuration

**Required Environment Variables (Production):**
- `SYNOPTICDATA_API_KEY` - Synoptic weather data API key
- `AWS_REGION` - AWS region for SES (e.g., us-west-1)
- `AWS_ACCESS_KEY_ID` - AWS access key for SES
- `AWS_SECRET_ACCESS_KEY` - AWS secret access key for SES
- `RENDER` - Auto-set by Render platform (used to detect production)

**Optional Environment Variables:**
- `DEBUG_API_RESPONSES` - Enable detailed API response logging (default: false)
- `THRESH_TEMP` - Temperature threshold in °F (default: 75)
- `THRESH_HUMID` - Humidity threshold in % (default: 15)
- `THRESH_WIND` - Wind speed threshold in mph (default: 10)
- `THRESH_GUSTS` - Wind gust threshold in mph (default: 15)
- `THRESH_SOIL_MOIST` - Soil moisture threshold in % (default: 10)

**Secrets Location:**
- Local development: `.env` file (git-ignored)
- Production (Render): Environment variables set in Render dashboard
- No vault integration (HashiCorp Vault, AWS Secrets Manager, etc.)

## Webhooks & Callbacks

**Incoming:**
- None detected - No webhook endpoints for external services

**Outgoing:**
- None detected - Application does not call external webhooks
- However, it sends emails via AWS SES to subscribed users when fire risk level transitions

## Data Integration Points

**Import/Export:**
- CSV file import: `file_processor.py` handles CSV parsing
- Excel file import: `.xlsx` parsing via openpyxl
- Subscriber bulk import: `bulk_import_subscribers()` in `subscriber_service.py`
- No export endpoints detected

## API Response Handling

**Fallback Strategy:**
- Synoptic API failures trigger automatic fallback to cached JSON data
- Fallback data path: `data/synoptic_fallback_data.json`
- Failure scenarios that trigger fallback:
  - 401 Unauthorized (token invalid/expired)
  - 403 Forbidden (account access restricted)
  - Connection timeouts
  - Network connection errors
  - Missing STATION field in response
  - Max retry attempts exceeded

**Data Freshness:**
- Background refresh every 10 minutes via `refresh_data_cache()`
- Data considered stale after 30 minutes without update
- Force refresh available on demand via `wait_for_fresh` query parameter

---

*Integration audit: 2026-01-21*

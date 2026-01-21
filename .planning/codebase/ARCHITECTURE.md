# Architecture

**Analysis Date:** 2026-01-21

## Pattern Overview

**Overall:** Layered REST API with real-time data polling and caching

**Key Characteristics:**
- FastAPI-based HTTP server with async request handling
- Multi-layer architecture: API clients → data processing → business logic → HTTP endpoints
- In-memory cache with async update events for data freshness coordination
- Background task scheduling for non-blocking cache updates
- Session-based admin authentication with PIN verification
- Email alert system with dual notification modes (Orange-to-Red transitions, custom alerts)

## Layers

**Application Layer (HTTP Endpoints):**
- Purpose: Handle HTTP requests, manage sessions, coordinate responses
- Location: `main.py` (FastAPI setup), `endpoints.py` (public endpoints), `admin_endpoints.py` (admin endpoints), `dev_endpoints.py` (development/debug endpoints)
- Contains: Request handlers, response formatting, session management, authentication
- Depends on: Cache, fire risk logic, email service, subscriber service
- Used by: Browser clients, API consumers

**Business Logic Layer:**
- Purpose: Calculate fire risk levels, determine alert conditions, apply manual overrides
- Location: `fire_risk_logic.py`
- Contains: Risk calculation algorithm, threshold comparisons, override mapping
- Depends on: Configuration constants (thresholds)
- Used by: Cache refresh, endpoints

**Data Processing Layer:**
- Purpose: Transform raw API responses into normalized weather data structures
- Location: `data_processing.py`
- Contains: Synoptic API parsing, field extraction, data aggregation, timezone handling
- Depends on: Configuration (station IDs, timezone)
- Used by: Cache refresh, fallback logic

**Caching Layer:**
- Purpose: Store and serve weather data with staleness tracking, fallback handling
- Location: `cache.py` (main cache object), `cache_refresh.py` (refresh orchestration)
- Contains: DataCache class, disk persistence, update events, cached field tracking
- Depends on: Configuration, data processing, API clients
- Used by: Endpoints, cache refresh

**API Integration Layer:**
- Purpose: Fetch data from external services with error handling and fallback
- Location: `api_clients.py`
- Contains: Synoptic API token generation, data fetching, retries, fallback data loading
- Depends on: Configuration (API keys), requests library
- Used by: Cache refresh

**Service Layers:**
- Email Service (`email_service.py`): Send alerts via AWS SES with HTML templates
- Subscriber Service (`subscriber_service.py`): Manage subscriber list in SQLite
- Admin Service (`admin_service.py`): Verify PIN, manage admin sessions
- File Processor (`file_processor.py`): Parse CSV/XLSX for bulk subscriber import

## Data Flow

**Initial Startup (Lifespan Event):**
1. FastAPI app starts with lifespan context manager (`main.py`)
2. Calls `refresh_data_cache(force=True)` to populate initial data
3. Waits for update event to complete
4. Logs success/failure and continues serving requests

**Periodic/On-Demand Data Refresh:**
1. Client calls `/fire-risk` endpoint
2. Endpoint checks cache staleness (60-minute threshold)
3. If stale or `wait_for_fresh` requested:
   - Call `refresh_data_cache(force=True)` to start async refresh
   - Wait for `data_cache.update_event` with timeout (30s)
4. Return cached fire risk data to client

**Refresh Cycle (Inside `cache_refresh.py`):**
1. Set `update_in_progress = True`
2. Call `get_synoptic_data()` to fetch weather from API
3. Call `process_synoptic_data()` to parse into weather fields
4. Apply admin overrides if test mode enabled
5. Call `calculate_fire_risk()` to determine alert level
6. Check if risk level changed (Orange → Red): send email alerts
7. Update cache with new data, save to disk
8. Signal update completion via `_update_complete_event.set()`

**Alert Generation Flow (Orange-to-Red Transition):**
1. Risk level changes from Orange to Red
2. Check if transition occurred today (calendar day limit)
3. If not yet today: call `send_orange_to_red_alert()`
4. Gets active subscribers from `subscribers.db`
5. Renders email template with weather data
6. Sends via AWS SES to subscriber list
7. Records alert timestamp in cache

**State Management:**
- **Synoptic Data**: Raw JSON from API, stored in `data_cache.synoptic_data`
- **Fire Risk Data**: Processed result `{"risk": "Red"|"Orange"|"Green", "explanation": str, "weather": {...}}`
- **Cached Fields**: Dict tracking which fields use fallback data `{"temperature": bool, ...}`
- **Last Valid Data**: Individual field timestamps, persists across restarts via disk cache
- **Update Event**: Async event that signals refresh completion to waiting requests
- **Test Mode**: Session-based override values stored in `admin_sessions[token]`

## Key Abstractions

**DataCache:**
- Purpose: Singleton cache object coordinating all cached data and update state
- Files: `cache.py`
- Pattern: In-memory data store with async event signaling, disk persistence, field-level metadata
- Key methods: `update_cache()`, `is_stale()`, `is_critically_stale()`, `wait_for_update()`, `reset_update_event()`

**Request Lifecycle:**
- Purpose: Coordinate HTTP request → cache check → possible refresh → response
- Files: `endpoints.py`
- Pattern: Async endpoint checks cache state, triggers refresh if needed, waits with timeout
- Handles staleness gracefully - returns stale data rather than blocking indefinitely

**API Token Management:**
- Purpose: Exchange permanent API key for temporary token with retry logic
- Files: `api_clients.py::get_api_token()`
- Pattern: Get token on demand, cache briefly, fallback to permanent key if token fails

**Admin Session Handling:**
- Purpose: Maintain authenticated admin state without database
- Files: `admin_endpoints.py::admin_sessions`
- Pattern: In-memory dict mapping random token → session data, cookies carry token
- Data: Override values (temperature, humidity, wind, soil moisture)

## Entry Points

**Application Startup:**
- Location: `main.py`
- Triggers: Application server start command
- Responsibilities: Create FastAPI app, register routes, set up CORS, initialize lifespan, mount static files

**Main HTTP Endpoint:**
- Location: `endpoints.py::fire_risk()`
- Triggers: GET `/fire-risk` request
- Responsibilities: Check cache staleness, trigger refresh if needed, return fire risk data

**Root/Home:**
- Location: `endpoints.py::home()`
- Triggers: GET `/` request
- Responsibilities: Serve dashboard HTML file

**Admin Dashboard:**
- Location: `admin_endpoints.py::admin_page()`
- Triggers: GET `/admin` request
- Responsibilities: Check session auth, serve admin panel HTML

**Admin API Routes:**
- Location: `admin_endpoints.py` (various endpoints)
- Triggers: POST requests to `/admin/*`
- Responsibilities: Login, logout, override test conditions, import subscribers, send test alerts

**Development/Debug Endpoints:**
- Location: `dev_endpoints.py` (available only in dev mode)
- Triggers: GET `/dev/*` requests
- Responsibilities: Diagnostic info, API testing, cache debugging (disabled in production)

## Error Handling

**Strategy:** Graceful degradation with fallback data

**Patterns:**
- **API Failures**: Log error, use `last_valid_data` stored in cache, fall back to default values
- **Missing Fields**: Individual field timestamps allow per-field fallback (e.g., wind data missing, others fresh)
- **Stale Data**: Mark with `cached_fields` metadata, still serve but flag in response
- **Cache Update Timeouts**: Return existing cache data, log warning about timeout
- **Disk Cache Load Failures**: Initialize with hardcoded defaults in `DataCache.DEFAULT_VALUES`

## Cross-Cutting Concerns

**Logging:**
- Centralized setup in `config.py` via Python logging module
- All modules import `logger` from config
- File: No persistent log file (uses stdout, captured by deployment platform)
- Pattern: Contextual INFO/WARNING/ERROR messages with data context

**Validation:**
- Email validation via regex in `file_processor.py::is_valid_email()`
- Pin verification in `admin_service.py::verify_pin()` (hardcoded check)
- Pydantic models for request bodies (`admin_endpoints.py::TestConditionsPayload`, `CustomEmailPayload`)

**Authentication:**
- PIN-based admin access via cookies + session tokens
- Public endpoints (fire risk, dashboard) have no auth
- Test mode flag is per-session, managed in-memory

**Timezone Handling:**
- Configured centralized in `config.py` as `TIMEZONE = pytz.timezone('America/Los_Angeles')`
- Applied consistently in: cache timestamps, alert calendar limits, data processing
- File: `data_processing.py::format_age_string()` formats time deltas with timezone awareness

---

*Architecture analysis: 2026-01-21*

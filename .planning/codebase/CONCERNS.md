# Codebase Concerns

**Analysis Date:** 2026-01-21

## Tech Debt

**Hardcoded Admin PIN:** (resolved: replaced by the `ADMIN_PASSWORD` environment variable)

**Weak PIN Hashing:**
- Issue: PIN uses SHA256 without salt (`admin_service.py` line 26), vulnerable to rainbow table attacks
- Files: `admin_service.py`
- Impact: If PIN hash is compromised, attacker can reverse it; not suitable for production security
- Fix approach: Use bcrypt or Argon2 with proper salting; consider longer than 4-digit PIN

**Weak Session Security:**
- Issue: Session tokens stored in plain in-memory dictionary; no session validation beyond existence check (`admin_endpoints.py` lines 48-121)
- Files: `admin_endpoints.py`
- Impact: Lost on server restart; vulnerable if memory is dumped; httponly=False allows JavaScript access to token
- Fix approach: Use secure session middleware (e.g., FastAPI sessions with Redis/database backend); set httponly=True; implement session expiration

**Overly Complex Cache State Management:**
- Issue: Cache state tracking spread across multiple flags (using_cached_data, cached_fields dict, wind-specific logic)
- Files: `cache.py`, `cache_refresh.py`
- Impact: Difficult to reason about correct state; wind_speed/wind_gust cached field detection has special case logic (lines 166-189)
- Fix approach: Consolidate cache state into single source of truth; remove conditional wind-specific handling

**Debug Logging in Production:**
- Issue: Excessive debug logging remains in production: fire_risk_logic.py lines 118-142 log every calculation step
- Files: `fire_risk_logic.py`, `cache_refresh.py`, `cache.py`, `api_clients.py`
- Impact: Performance degradation; unnecessary log volume; may expose sensitive calculation details
- Fix approach: Move detailed logging to DEBUG level; use environment variable to control verbosity

**Unused Configuration Variables:**
- Issue: Environment variables defined but unused: STATION_ID, DEBUG, WUNDERGROUND_API_KEY
- Files: `config.py` (commented out lines 30, 39, 59-60), `system-overview.md` line 71, 76
- Impact: Confusion about what's actually used; dead code increases maintenance burden
- Fix approach: Remove references; document why they were deprecated

**Cookie Security Settings:**
- Issue: Session cookie has httponly=False (admin_endpoints.py line 117), allowing JavaScript access
- Files: `admin_endpoints.py`
- Impact: XSS vulnerabilities can steal session tokens; line 119 has secure=False for non-HTTPS
- Fix approach: Set httponly=True in production; set secure=True with HTTPS

## Known Bugs

**Wind Data Cached Field Detection:**
- Symptoms: Wind speed and wind gust cached field flags may incorrectly reflect cache status
- Files: `cache.py` lines 166-189, `cache_refresh.py` (cache state update logic)
- Trigger: When wind data is missing and fallback is used, the cached_fields tracking may not reflect actual source
- Workaround: System forces second refresh at startup to ensure wind data is fresh (main.py lines 26-35)
- Note: main.py contains defensive refresh logic suggesting this is known fragile area

**Orange-to-Red Alert Email Template Missing:**
- Symptoms: Email service fails gracefully but uses fallback plain text instead of HTML template
- Files: `email_service.py` line 147 (TODO comment)
- Trigger: When orange_to_red_alert.html or orange_to_red_alert.txt templates are missing from ./templates/
- Impact: Alerts sent with basic formatting instead of designed templates
- Fix approach: Create missing templates or remove dependency on template files

**Hardcoded Station IDs:**
- Symptoms: Weather stations hardcoded; no flexibility for geographic changes
- Files: `config.py` lines 34-36, `data_processing.py` line 11
- Trigger: Any change to monitoring location requires code changes
- Impact: Application cannot be reused for different geographic areas without modification
- Fix approach: Make station IDs environment variables with documented defaults

**Test Mode State Persistence:**
- Symptoms: Test mode (using cached data) state persists across browser sessions if user doesn't manually toggle
- Files: `cache.py`, `admin_endpoints.py` (test mode toggle endpoint)
- Trigger: User sets test mode, logs out, logs back in later - test mode still active
- Impact: Accidental testing with cached data in production
- Fix approach: Bind test mode to session, reset on login, or auto-disable after time window

## Security Considerations

**API Key Exposure Risk in Logs:**
- Risk: API key appears in token URL logged to console (api_clients.py line 55 logs to info level, but logs are suppressed by DEBUG_API_RESPONSES flag)
- Files: `api_clients.py` lines 54-55, `check_wind_data.py`
- Current mitigation: DEBUG_API_RESPONSES defaults to false; logs only raw responses not URLs
- Recommendations:
  - Mask API keys in logs completely; log placeholder like "API_KEY_SET" instead
  - Implement structured logging that never includes secrets
  - Scan logs for accidentally logged credentials

**PIN Exposed in Client-Side JavaScript:**
- Risk: If JavaScript code is decompiled, PIN visible in plaintext on client side (not actually exposed in current code - validation is server-side only)
- Files: `admin_endpoints.py` (server-side validation only)
- Current mitigation: PIN verification happens on server (line 103); JavaScript only submits form
- Recommendations: Continue enforcing server-side validation; document that server is authoritative source

**Database Not Protected:**
- Risk: SQLite database file `subscribers.db` stored locally; no encryption; accessible to anyone with file system access
- Files: `subscriber_service.py` line 6, `subscribers.db`
- Current mitigation: Database stored in application directory with file permissions
- Recommendations:
  - Document database backup procedures
  - Implement at-rest encryption for subscriber email list (sensitive PII)
  - Consider moving to managed database service in production

**AWS Credentials in Environment:**
- Risk: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY stored as environment variables; if environment is leaked, attacker can send emails via SES
- Files: `email_service.py` lines 38-40
- Current mitigation: Render manages environment variables; credentials stored in platform secrets
- Recommendations:
  - Use IAM roles instead of credentials if possible
  - Implement SES rate limiting and monitoring
  - Create dedicated IAM user with minimal SES permissions (SendEmail only)

**CORS Configuration:**
- Risk: CORS allows only two specific origins (main.py lines 65-71), but both are hardcoded
- Files: `main.py` lines 65-71
- Current mitigation: Origins are explicitly listed, not wildcard
- Recommendations:
  - Move CORS origins to environment variables
  - Document which origins are needed for production deployment

## Performance Bottlenecks

**Synchronous Database Operations:**
- Problem: Database queries are synchronous blocking calls in async endpoint handlers
- Files: `subscriber_service.py` (get_db_connection uses sqlite3, blocking calls)
- Cause: SQLite doesn't support async; blocking calls in async handlers tie up event loop
- Improvement path:
  - Use asyncio.run_in_executor() to offload database calls to thread pool
  - Consider migration to async-compatible database (PostgreSQL with asyncpg)
  - Add connection pooling

**API Token Fetched Every Request:**
- Problem: `get_api_token()` called for every weather data fetch, doesn't cache tokens
- Files: `api_clients.py` line 142, called from `cache_refresh.py`
- Cause: No token caching mechanism; each request hits Synoptic API twice (auth + data)
- Improvement path: Cache token with TTL; implement token refresh logic; validate token before fetching

**Full Data Refresh on Every Stale Check:**
- Problem: Cache refresh fetches all stations even if only one field is needed
- Files: `cache_refresh.py` line 80+ (refresh_data_cache function)
- Cause: Monolithic data fetch; no per-field refresh capability
- Improvement path: Implement field-level caching; allow partial refreshes

**Exponential Backoff Not Used in All Retry Paths:**
- Problem: Only some API calls use exponential backoff; inconsistent retry strategy
- Files: `api_clients.py` implements backoff but not all error paths use it uniformly
- Cause: Retry logic scattered across multiple functions
- Improvement path: Centralize retry logic with consistent backoff strategy

## Fragile Areas

**Cache.py Update Logic:**
- Files: `cache.py` lines 122-249 (update_cache method)
- Why fragile:
  - Complex conditional logic for determining if wind data is cached (lines 166-189)
  - State recalculation based on presence of None values (line 194)
  - Multiple inter-dependent state updates in single method
- Safe modification:
  - Add comprehensive unit tests for all cache state transitions
  - Consider splitting update_cache into smaller methods (update_wind, update_temperature, etc.)
  - Add explicit state validation after each update
- Test coverage: Gaps in integration between cache state and actual data freshness

**Fire Risk Calculation:**
- Files: `fire_risk_logic.py` lines 16-172
- Why fragile:
  - Manual override key mapping (lines 8-14) must match frontend field names
  - Temperature unit conversion happens in multiple places (lines 39, 65, 92, 106)
  - All conditions must be met using AND logic (line 141); no other risk levels supported
  - Default values used if any metric is None (lines 92-96); may mask data availability issues
- Safe modification:
  - Add integration tests with admin override endpoint to verify key mapping
  - Centralize temperature conversion to single function
  - Document assumption that all thresholds must be exceeded for Red level
- Test coverage: Tests verify calculation but not key mapping validation

**Email Alert Triggering:**
- Files: `cache_refresh.py` lines 235-280+ (email alert logic)
- Why fragile:
  - State transition tracking (previous_risk_level) stored in memory cache object
  - Orange-to-Red transition requires template files that may not exist
  - Alert rate limiting based on timestamp; can fail if clock adjusted
  - Daily email limit checked but can be overridden by admin (admin_endpoints.py)
- Safe modification:
  - Persist state transitions to database instead of memory
  - Make email templates required; fail fast if missing
  - Document timestamp assumptions and timezone handling
  - Add explicit tests for state transition edge cases (repeated transitions, admin overrides)
- Test coverage: Tests exist but limited to happy path scenarios

**Admin Endpoints Session Handling:**
- Files: `admin_endpoints.py` lines 54-95 (admin page GET)
- Why fragile:
  - Session token validity checked only by presence in dict (line 61)
  - HTML string manipulation with replace() for authentication state (lines 74, 77, 80-81)
  - No session expiration cleanup; sessions accumulate in memory
  - Pin form visibility toggled via string replacement rather than template variables
- Safe modification:
  - Implement proper session middleware with expiration
  - Use template engine for conditional rendering instead of string replace
  - Add session cleanup on startup and periodically
  - Add explicit tests for session edge cases (expired, invalid, missing tokens)
- Test coverage: Very limited; mostly integration tests

## Scaling Limits

**In-Memory Session Storage:**
- Current capacity: Limited by server RAM; fails silently if memory exhausted
- Limit: Server restart loses all sessions; multiple server instances can't share sessions
- Scaling path:
  - Move to Redis-backed sessions (supports cluster deployments)
  - Implement session expiration and cleanup
  - Add monitoring for session count

**SQLite Database Scaling:**
- Current capacity: Single-file database fine for thousands of subscribers; becomes slow at 100k+
- Limit: SQLite not designed for concurrent writes; locking issues under high load
- Scaling path:
  - Migrate to PostgreSQL for production (supports concurrent connections)
  - Add database indexing strategy
  - Implement connection pooling
  - Use read replicas for reporting

**Single Synoptic API Fallback:**
- Current capacity: Application relies on one primary API; fallback is local cache only
- Limit: If Synoptic API is permanently unavailable, system can only serve cached data up to data_timeout_threshold (30 minutes)
- Scaling path:
  - Add secondary weather data source (Weather Underground, NOAA)
  - Implement hybrid data sources with priority ranking
  - Extend cache retention period with aging data indicator

**Background Email Queue:**
- Current capacity: Emails sent synchronously in background tasks; no queue
- Limit: If email service is slow, background tasks can back up
- Scaling path:
  - Implement proper message queue (Redis, RabbitMQ, AWS SQS)
  - Add email sending worker pool
  - Implement exponential backoff for SES failures

## Dependencies at Risk

**Boto3/AWS SES Dependency:**
- Risk: Tight coupling to AWS SES; no abstraction layer for email sending
- Impact: If AWS SES becomes unavailable or costs spike, major refactoring required
- Migration plan:
  - Create email_provider abstraction interface
  - Implement alternative providers (SendGrid, Mailgun)
  - Add provider selection via environment variable

**Synoptic API Hard Dependency:**
- Risk: Application cannot function without Synoptic API; single point of failure
- Impact: If API changes or becomes unavailable, dashboard becomes useless
- Migration plan:
  - Document fallback strategy (cached data only)
  - Add configurable timeout thresholds
  - Implement circuit breaker pattern
  - Add health check endpoint

**FastAPI/Starlette Version Compatibility:**
- Risk: Python web framework; pins to fastapi==0.115.11
- Impact: Security patches may require version upgrades with breaking changes
- Migration plan:
  - Implement dependency upgrade testing in CI/CD
  - Document known incompatibilities
  - Plan major version migrations with feature flag support

**Pandas/Numpy for Data Processing:**
- Risk: Large dependencies included but only minimal usage (mainly in tests)
- Impact: Increases deployment size; unnecessary dependency
- Migration plan:
  - Audit actual usage of pandas/numpy
  - Replace with lightweight alternatives (built-in dict/list operations)
  - Remove if not actively used

## Missing Critical Features

**No Audit Logging:**
- Problem: Admin actions (overrides, test mode toggles) not logged to persistent storage
- Blocks: Cannot investigate who made what changes or when
- Recommendation: Add audit log table with: timestamp, admin_ip, action, details, result

**No Monitoring/Alerting:**
- Problem: Application has no visibility into its own health; errors only visible in logs
- Blocks: Cannot proactively detect failures; reactive troubleshooting only
- Recommendation: Integrate with monitoring service (Sentry for errors, Datadog for metrics)

**No Backup Strategy for Subscribers:**
- Problem: Subscriber database has no backup; loss of single file means loss of all subscriber data
- Blocks: Cannot recover from data loss; no audit trail
- Recommendation: Implement automated daily backups with retention policy

**No Rate Limiting on Public API:**
- Problem: /fire-risk endpoint has no rate limiting; vulnerable to DOS
- Blocks: Bad actors can cause service degradation
- Recommendation: Implement rate limiting middleware (e.g., SlowAPI)

**No Admin Activity Timestamps:**
- Problem: Test mode toggles and overrides not timestamped; unclear when changes occurred
- Blocks: Cannot correlate fire risk anomalies with admin testing
- Recommendation: Add created_at/updated_at timestamps to override data

## Test Coverage Gaps

**No E2E Tests for Admin Overrides:**
- What's not tested: Admin manually setting weather values and verifying fire risk recalculates correctly
- Files: `tests/` directory (no integration test for admin override flow)
- Risk: Override feature could silently fail; no test catches it
- Priority: High (core admin feature)

**No Tests for Cache Persistence:**
- What's not tested: Cache properly loads from disk on server startup; cache survives server restart
- Files: `cache.py` (disk persistence logic), `tests/` (no test_cache_persistence_on_startup.py)
- Risk: Server restart could lose data; users see stale/empty data after restart
- Priority: High (availability critical)

**No Tests for Email State Transitions:**
- What's not tested: Orange-to-Red alert triggered exactly once on transition; not repeated on every cycle
- Files: `cache_refresh.py` (email alert logic), `tests/test_email_orange_to_red.py` (exists but limited)
- Risk: Users receive duplicate alert emails; system sends alerts at wrong time
- Priority: High (user experience)

**No Tests for Concurrent API Calls:**
- What's not tested: Multiple simultaneous /fire-risk requests while background cache refresh is running
- Files: `endpoints.py`, `cache.py`, `cache_refresh.py`
- Risk: Race conditions in cache state updates; inconsistent data served
- Priority: Medium (production load condition)

**No Tests for Synoptic API Failure Scenarios:**
- What's not tested: 401 errors, timeouts, partial responses, malformed JSON responses
- Files: `api_clients.py`, `tests/test_api_clients.py`
- Risk: Application crashes instead of gracefully degrading
- Priority: Medium (production resilience)

**No Tests for Database Concurrent Access:**
- What's not tested: Multiple threads/processes accessing subscriber database simultaneously
- Files: `subscriber_service.py`, `tests/` (only single-threaded tests)
- Risk: Database corruption or locking; email imports could fail under concurrent load
- Priority: Medium (data integrity)

**No Tests for Invalid Admin PIN Values:**
- What's not tested: PIN containing special characters, empty PIN, null PIN
- Files: `admin_service.py`, `tests/` (no comprehensive input validation tests)
- Risk: Edge case crashes or bypasses
- Priority: Low (affects admin interface only)

---

*Concerns audit: 2026-01-21*

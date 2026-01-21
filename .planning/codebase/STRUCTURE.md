# Codebase Structure

**Analysis Date:** 2026-01-21

## Directory Layout

```
/Users/david/Documents/Coding/dev/fire-risk-dashboard/
├── main.py                          # FastAPI app initialization, lifespan, route registration
├── config.py                        # Environment config, constants, logging setup
├── endpoints.py                     # Public API routes (/fire-risk, /)
├── admin_endpoints.py               # Admin routes (/admin, /admin/*)
├── dev_endpoints.py                 # Development debugging routes (/dev/*) - production disabled
│
├── cache.py                         # DataCache class with persistence
├── cache_refresh.py                 # Data refresh orchestration, alert triggering
├── api_clients.py                   # Synoptic API integration, token management
│
├── data_processing.py               # Weather data parsing, field extraction
├── fire_risk_logic.py               # Fire risk calculation, threshold evaluation
│
├── email_service.py                 # AWS SES email sending, template rendering
├── subscriber_service.py            # SQLite subscriber management
├── admin_service.py                 # PIN verification, session management
├── file_processor.py                # CSV/XLSX parsing for bulk imports
│
├── requirements.txt                 # Python dependencies (FastAPI, boto3, pandas, etc)
├── requirements-dev.txt             # Dev dependencies (pytest, coverage)
├── pytest.ini                       # Pytest configuration
├── .env                            # Environment variables (local dev only)
├── .gitignore                      # Git exclude patterns
│
├── static/                         # Served static assets
│   ├── dashboard.html              # Main dashboard UI
│   ├── admin.html                  # Admin panel UI
│   ├── api-tester.html            # Development API testing tool
│   ├── css/
│   │   └── dashboard.css          # Dashboard styling
│   └── js/
│       ├── dashboard.js            # Dashboard client-side logic
│       └── admin_test_conditions.js # Admin override controls
│
├── templates/                      # Email templates (Jinja2)
│   ├── orange_to_red_alert.html   # HTML version of Orange-to-Red alert
│   └── orange_to_red_alert.txt    # Text version of Orange-to-Red alert
│
├── data/                           # Persistent data storage
│   ├── weather_cache.json         # Cached weather/fire-risk data (disk persistence)
│   ├── synoptic_fallback_data.json # Fallback API response for offline mode
│   └── test_weather_cache.json    # Test data snapshot
│
├── subscribers.db                  # SQLite database for email subscribers
│
├── tests/                          # Test suite
│   ├── conftest.py                # Pytest fixtures (client, reset_cache, mocks)
│   ├── test_endpoints.py          # Tests for public API endpoints
│   ├── test_cache_system.py       # Tests for cache update logic
│   ├── test_cache_refresh.py      # Tests for refresh orchestration
│   ├── test_data_processing.py    # Tests for Synoptic data parsing
│   ├── test_fire_risk_logic.py    # Tests for risk calculation
│   ├── test_email_service.py      # Tests for SES integration
│   ├── test_subscriber_service.py # Tests for subscriber DB
│   ├── test_integration.py        # End-to-end flow tests
│   ├── test_e2e.py               # Browser-based E2E tests (Playwright)
│   ├── mock_utils.py             # Shared mock data
│   ├── debug_csv_processor.py    # CSV parsing debugging helper
│   ├── debug_xlsx_reader.py      # XLSX parsing debugging helper
│   └── [33 more test files...]   # Specific scenario tests
│
└── .planning/                     # GSD planning documents
    └── codebase/                  # This directory
        ├── ARCHITECTURE.md        # You are reading this
        └── STRUCTURE.md           # This file
```

## Directory Purposes

**Root:**
- Purpose: Python modules for API server, data processing, services
- Contains: Main application code, configuration, persistent data
- Key files: `main.py` (entry point), `config.py` (constants), `cache.py` (core state)

**static/:**
- Purpose: Web assets served directly to browsers
- Contains: HTML pages, CSS styling, JavaScript client code
- Key files: `dashboard.html` (main UI), `admin.html` (admin panel)
- Generated: No
- Committed: Yes

**static/js/:**
- Purpose: Client-side JavaScript logic
- Contains: Dashboard interactions, API calls from browser, admin controls
- Key files: `dashboard.js` (main logic), `admin_test_conditions.js` (test override UI)

**static/css/:**
- Purpose: Stylesheet definitions
- Contains: Dashboard layout, color schemes, responsive design
- Key files: `dashboard.css`

**templates/:**
- Purpose: Email template files (Jinja2 format)
- Contains: HTML and text versions of alert emails
- Key files: `orange_to_red_alert.html`, `orange_to_red_alert.txt`
- Generated: No
- Committed: Yes

**data/:**
- Purpose: Local persistent storage for cache and fallback data
- Contains: JSON files for disk cache, fallback API responses
- Key files: `weather_cache.json` (cache on disk), `synoptic_fallback_data.json` (offline fallback)
- Generated: Yes (created at runtime)
- Committed: Yes (with sample data)

**tests/:**
- Purpose: Test suite for all modules
- Contains: Unit tests, integration tests, fixtures, mocks
- Key files: `conftest.py` (fixtures), `test_endpoints.py` (API tests)
- Generated: Yes (pytest creates __pycache__)
- Committed: Yes (all test files)

## Key File Locations

**Entry Points:**
- `main.py`: Application server entry point, FastAPI initialization, lifespan management
- `static/dashboard.html`: Web browser entry point for public dashboard
- `static/admin.html`: Admin panel entry point

**Configuration:**
- `config.py`: All constants, thresholds, API keys, timezone, logging
- `.env`: Local development only (not in production)
- `requirements.txt`: All Python package dependencies

**Core Logic:**
- `fire_risk_logic.py`: Fire risk calculation algorithm
- `data_processing.py`: Parse Synoptic API responses into weather data
- `cache.py`: DataCache class definition, in-memory state management
- `cache_refresh.py`: Data refresh orchestration, alert triggering

**Data Access:**
- `api_clients.py`: Synoptic API integration
- `subscriber_service.py`: SQLite database access
- `email_service.py`: AWS SES email integration

**HTTP Routes:**
- `endpoints.py`: Public routes (`GET /fire-risk`, `GET /`)
- `admin_endpoints.py`: Admin routes (`GET /admin`, `POST /admin/login`, etc)
- `dev_endpoints.py`: Development debug routes (`GET /dev/check-env`, etc)

**Testing:**
- `tests/conftest.py`: Pytest fixtures and configuration
- `tests/test_*.py`: Individual test modules by feature area

## Naming Conventions

**Files:**
- Module files: snake_case (e.g., `data_processing.py`, `api_clients.py`)
- Test files: `test_[module_name].py` (e.g., `test_cache_refresh.py`)
- Config files: either lowercase (`.env`, `config.py`) or uppercase (`.gitignore`)
- Static assets: lowercase with hyphenated names (e.g., `dashboard.html`, `red-banner-mockup.html`)

**Directories:**
- Package dirs: lowercase plural where applicable (`tests/`, `static/`, `data/`, `templates/`)
- Special dirs: lowercase with hyphen prefix (`.github/`, `.planning/`, `.pytest_cache/`)

**Python Functions:**
- Async functions with `async def` prefix
- Public functions: `snake_case`
- Private helpers: `_snake_case` prefix
- API endpoints: start with HTTP method context (e.g., `async def fire_risk()`)

**Python Classes:**
- PascalCase (e.g., `DataCache`, `CustomEmailPayload`)

**Variables:**
- Globals from environment: UPPERCASE (e.g., `IS_PRODUCTION`, `SYNOPTIC_API_KEY`)
- Local/module globals: snake_case (e.g., `admin_sessions`, `FALLBACK_DATA_PATH`)
- Instance attributes: snake_case (e.g., `data_cache.fire_risk_data`)

## Where to Add New Code

**New Feature (e.g., new data source, new alert type):**
- Primary code: Root module named after feature (`new_source.py` or add to `api_clients.py`)
- Integration: Update `cache_refresh.py` to call new code
- Tests: `tests/test_[feature_name].py`
- Config constants: Add to `config.py`

**New Component/Module:**
- Implementation: Add `.py` file to root directory if part of core logic
- If it's a service: Follow pattern of `email_service.py`, `subscriber_service.py`
- Tests: Create `tests/test_[module_name].py`
- Imports: Update `endpoints.py` or `cache_refresh.py` to use new module

**New Endpoint:**
- Public endpoint: Add function to `endpoints.py`
- Admin endpoint: Add function to `admin_endpoints.py`
- Development endpoint: Add to `dev_endpoints.py`
- Pattern: Use `@router.get()` or `@router.post()` decorators
- Include doc string with Args/Returns
- Return JSON via `JSONResponse()` or FastAPI auto-serialization

**Utilities/Helpers:**
- Data processing helpers: Add to `data_processing.py`
- File parsing helpers: Add to `file_processor.py`
- Shared utilities: Create new `utils.py` file

**Static Assets:**
- HTML pages: `static/[page_name].html`
- Stylesheets: `static/css/[component_name].css`
- Client scripts: `static/js/[component_name].js`

**Email Templates:**
- HTML version: `templates/[alert_type].html`
- Text version: `templates/[alert_type].txt`
- Usage: Reference in `email_service.py` with Jinja2 rendering

## Special Directories

**.planning/codebase/:**
- Purpose: GSD-generated architecture and planning documents
- Generated: Yes (by GSD commands)
- Committed: Yes
- Contents: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, etc

**.github/workflows/:**
- Purpose: CI/CD pipeline definitions
- Generated: No
- Committed: Yes
- Contents: GitHub Actions YAML files for running tests

**.pytest_cache/:**
- Purpose: Pytest internal cache
- Generated: Yes
- Committed: No (in .gitignore)

**.vscode/:**
- Purpose: VS Code workspace settings
- Generated: No
- Committed: Yes
- Contents: Editor configuration, debug settings

**__pycache__/:**
- Purpose: Python bytecode cache
- Generated: Yes
- Committed: No (in .gitignore)

**.git/:**
- Purpose: Git repository data
- Generated: Yes
- Committed: N/A (not part of repo tracking)

**venv/:**
- Purpose: Python virtual environment
- Generated: Yes (when creating venv)
- Committed: No (in .gitignore)

**Feedback/ and ignore/:**
- Purpose: Archive/documentation directories
- Generated: No
- Committed: Yes
- Contents: User feedback, receipts, historical notes

## Path Patterns for Common Operations

**Access cached weather data:**
```python
from cache import data_cache
data_cache.fire_risk_data  # Current risk data
data_cache.last_valid_data  # Individual field history
data_cache.cached_fields  # Which fields are using fallback
```

**Get configuration values:**
```python
from config import THRESH_TEMP, THRESH_WIND, TIMEZONE, logger
```

**Make API requests:**
```python
from api_clients import get_synoptic_data
weather_data = get_synoptic_data()
```

**Send emails:**
```python
from email_service import send_orange_to_red_alert
from subscriber_service import get_active_subscribers
subscribers = get_active_subscribers()
await send_orange_to_red_alert(subscribers, weather_data)
```

**Access database:**
```python
from subscriber_service import add_subscriber, get_active_subscribers
emails = get_active_subscribers()
```

**Test with fixtures:**
```python
# In test file:
def test_something(client, reset_cache, mock_synoptic_response):
    # client: async HTTP client to app
    # reset_cache: fixture that clears cache before/after
    # mock_synoptic_response: fixture with sample API response
    pass
```

---

*Structure analysis: 2026-01-21*

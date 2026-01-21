# Technology Stack

**Analysis Date:** 2026-01-21

## Languages

**Primary:**
- Python 3.11+ - Entire backend and all business logic

**Secondary:**
- HTML/CSS/JavaScript - Frontend dashboard UI (`static/dashboard.html`, `static/js/dashboard.js`)

## Runtime

**Environment:**
- Python (CPython) - Local development and production

**Package Manager:**
- pip - Dependencies managed via `requirements.txt` and `requirements-dev.txt`
- Lockfile: Present via pip freeze, stored implicitly in version specifications

## Frameworks

**Core:**
- FastAPI 0.115.11 - Web framework for API endpoints and static file serving
- Uvicorn 0.34.0 - ASGI server for running FastAPI application
- Starlette 0.46.1 - ASGI web microframework (underlying layer for FastAPI)

**Templating:**
- Jinja2 3.1.6 - HTML email template rendering for alerts (`email_service.py` loads templates from `./templates/`)

**Data Processing:**
- pandas 2.2.3 - Data analysis and CSV/Excel file processing
- numpy 2.2.5 - Numerical operations, used by pandas

**Testing:**
- pytest 8.3.5 - Test runner and framework
- pytest-asyncio 0.26.0 - Async/await test support for FastAPI
- pytest-cov 4.1.0 - Code coverage reporting
- pytest-playwright 0.7.0 - Browser automation for E2E testing
- playwright 1.51.0 - Browser automation tool

**Build/Dev:**
- Pydantic 2.10.6 - Data validation and settings management for FastAPI request/response models
- python-dotenv 0.19.2 - Environment variable loading from .env files

## Key Dependencies

**Critical:**
- boto3 1.37.34 - AWS SDK for SES (email sending service)
- botocore 1.37.34 - Core AWS service library (required by boto3)
- requests 2.32.3 - HTTP client for external API calls (Synoptic API, fallback mechanisms)

**Infrastructure:**
- pytz 2024.1 - Timezone handling (America/Los_Angeles for Sierra City)
- python-dateutil 2.9.0 - Extended date/time utilities
- python-multipart 0.0.20 - Parsing multipart form data for file uploads

**Data Validation & Processing:**
- email_validator 2.2.0 - Email format validation for subscriber management
- openpyxl 3.1.5 - Excel file (.xlsx) reading/writing
- beautifulsoup4 4.12.2 - HTML parsing (email template processing)

**Networking:**
- httpx 0.27.0 - Modern async HTTP client (alternative to requests)
- httpcore 1.0.7 - Low-level HTTP client library
- urllib3 2.3.0 - HTTP client utilities
- certifi 2025.1.31 - SSL certificate bundle

**Utilities:**
- click 8.1.8 - CLI framework (for CLI utilities)
- python-slugify 8.0.4 - Convert text to URL-safe slugs
- six 1.17.0 - Python 2/3 compatibility utilities
- pluggy 1.5.0 - Plugin system (used by pytest)
- iniconfig 2.1.0 - INI file parsing (pytest config)
- packaging 24.2 - Package version parsing
- setuptools 58.2.0 - Package distribution utilities

## Configuration

**Environment:**
- `.env` file for local development (loaded via python-dotenv)
- Environment variables for production on Render platform
- Detection: `IS_PRODUCTION = os.getenv("RENDER") is not None` in `config.py`

**Key Configuration Files:**
- `config.py` - Centralized configuration loading (API keys, thresholds, timezone)
- `pytest.ini` - Test runner configuration with markers and asyncio settings
- `.env` - Local development environment variables (API keys, AWS credentials, thresholds)

**Configuration Variables:**
- `SYNOPTICDATA_API_KEY` - Synoptic weather API authentication
- `WUNDERGROUND_API_KEY` - Legacy (no longer used, present in .env but deprecated)
- `AWS_REGION` - AWS SES region (us-west-1)
- `AWS_ACCESS_KEY_ID` - AWS authentication
- `AWS_SECRET_ACCESS_KEY` - AWS authentication
- `DEBUG_API_RESPONSES` - Toggle detailed API logging
- `THRESH_TEMP`, `THRESH_HUMID`, `THRESH_WIND`, `THRESH_GUSTS`, `THRESH_SOIL_MOIST` - Fire risk thresholds
- `RENDER` - Present in production to indicate Render platform deployment

## Platform Requirements

**Development:**
- Python 3.11+
- pip package manager
- SQLite3 (embedded, no separate installation needed)
- Git for version control

**Production:**
- Render platform (PaaS - inferred from `IS_PRODUCTION` check and CORS allowing "https://fire-risk-dashboard.onrender.com")
- AWS account with SES service enabled (for email alerts)
- Synoptic API account with active subscription and valid API key

**Database:**
- SQLite3 - Embedded database for subscriber management (`subscribers.db`)
- File-based, no separate database server required

## Deployment

**Hosting Platform:**
- Render (referenced in CORS configuration and IS_PRODUCTION logic)
- Likely configured with Render's Python buildpack
- Application entry point: `uvicorn main:app --host 0.0.0.0 --port 8000` (inferred)

**Build Process:**
- GitHub Actions workflow for testing on push/PR to main (`.github/workflows/tests.yml`)
- Runs pytest on Python 3.11
- Test command: `python -m pytest tests/test_fire_risk_logic.py`

## Caching Strategy

**Data Cache:**
- In-memory cache via `DataCache` class (`cache.py`)
- Disk-based fallback cache: `data/weather_cache.json` (JSON serialization)
- Automatic refresh intervals: 10 minutes background refresh
- Data timeout threshold: 30 minutes (data considered stale)

---

*Stack analysis: 2026-01-21*

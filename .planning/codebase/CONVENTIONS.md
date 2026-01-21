# Coding Conventions

**Analysis Date:** 2026-01-21

## Naming Patterns

**Files:**
- Snake case for Python files: `fire_risk_logic.py`, `data_processing.py`, `api_clients.py`, `cache_refresh.py`
- Snake case for directories: `tests/`, `data/`
- HTML files in `static/`: kebab-case: `admin.html`, `api-tester.html`
- JavaScript files in `static/js/`: kebab-case: `dashboard.js`, `admin_test_conditions.js`

**Functions:**
- Python: Snake case: `calculate_fire_risk()`, `process_synoptic_data()`, `refresh_data_cache()`, `get_api_token()`
- JavaScript: Camel case: `fetchFireRisk()`, `fetchWithTimeout()`, `formatCacheInfo()`

**Variables:**
- Python module-level constants: UPPER_SNAKE_CASE: `SYNOPTIC_API_KEY`, `THRESH_TEMP`, `TIMEZONE`, `FALLBACK_DATA_PATH`
- Python variables: snake_case: `weather_data`, `fire_risk_data`, `current_time`, `synoptic_response`
- JavaScript variables: camelCase: `refreshInterval`, `maxRetries`, `waitForFreshTimeout`
- Python class attributes: snake_case: `self.synoptic_data`, `self.fire_risk_data`, `self.last_updated`, `self.update_in_progress`

**Types:**
- Python type hints used extensively: `Dict[str, Any]`, `Optional[str]`, `Tuple[str, str]`, `List[str]`
- Return types documented in docstrings: `Tuple of (air_temp, relative_humidity, wind_speed, wind_gust, soil_moisture_15cm, found_stations, missing_stations)`

## Code Style

**Formatting:**
- Python: Standard PEP 8 style observed
- Line length: Typically 80-100 characters
- Indentation: 4 spaces for Python, 2 spaces for JavaScript

**Linting:**
- No `.eslintrc` or `.prettierrc` files detected
- No black/isort configuration found
- Manual adherence to PEP 8 conventions

## Import Organization

**Order (Python):**
1. Standard library imports: `import os`, `import json`, `import logging`, `from typing import ...`
2. Third-party imports: `import requests`, `import pytest`, `import pytz`, `from fastapi import ...`
3. Local imports: `from config import ...`, `from cache import ...`, `from fire_risk_logic import ...`

**Pattern observed in `fire_risk_logic.py`:**
```python
from typing import Dict, Any, Tuple, Optional
from config import (
    THRESH_TEMP_CELSIUS, THRESH_HUMID, THRESH_WIND,
    THRESH_GUSTS, THRESH_SOIL_MOIST, logger
)
```

**Path Aliases:**
- No path aliases detected (no `jsconfig.json` or `tsconfig.json` with paths)
- Relative imports used in tests: `sys.path.insert(0, os.path.abspath(...))`

## Error Handling

**Patterns:**
- Try-except blocks with specific exception types: `except requests.exceptions.RequestException as e`
- Generic except clauses for fallbacks: `except: logger.error(...)`
- Return None or default values on error instead of raising
- Use of `logger.error()` for error logging throughout

**Example from `api_clients.py`:**
```python
try:
    response = requests.get(token_url, ...)
    response.raise_for_status()
    token_data = response.json()
except requests.exceptions.RequestException as e:
    logger.error(f"Error fetching API token: {e}")
    return None
```

**Fire risk logic error handling from `fire_risk_logic.py`:**
```python
try:
    # Risk calculation logic
    ...
except Exception as e:
    logger.error(f"Error calculating fire risk: {e}")
    return "Error", "Could not calculate risk", effective_values
```

## Logging

**Framework:** Python `logging` module via config

**Setup location:** `config.py`
```python
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
```

**Patterns:**
- Import logger from config: `from config import logger`
- Use emoji prefixes for clarity: `logger.info("🚀 Application startup...")`, `logger.error("❌ Failed to populate...")`
- Info level for normal operations and state changes
- Warning level for recoverable issues: `logger.warning("⚠️ Wind data still marked as cached...")`
- Error level for failures: `logger.error("❌ Failed to get weather data...")`

**Where to log:**
- Cache state changes (startup, refresh, updates)
- API calls and responses (with DEBUG_API_RESPONSES flag for verbose output)
- Data processing (station identification, field extraction)
- Error conditions with context

**Logging in JavaScript:**
- Uses `console.log()`, `console.warn()`, `console.error()` with emoji prefixes
- Debug logs include data structure details: `console.log('RESPONSE DEBUG: Cache info:', data.cache_info)`

## Comments

**When to Comment:**
- Explain WHY not WHAT for complex logic (code should be self-documenting)
- Mark intentional workarounds with context: `# Fixed 403 Forbidden errors from the Synoptic API`
- Document API behavior quirks: `# No longer using Weather Underground stations for wind gust data`
- Mark temporary fixes or known issues: No TODO markers heavily used; issues tracked in issues instead

**JSDoc/TSDoc:**
- Python functions use docstrings with triple quotes
- Standard format with Args, Returns sections

**Example from `fire_risk_logic.py`:**
```python
def calculate_fire_risk(
    weather: Dict[str, Any],
    manual_overrides: Optional[Dict[str, float]] = None
) -> Tuple[str, str, Dict[str, Any]]:
    """Determines fire risk level based on weather data and environmental thresholds,
    applying manual overrides if provided.

    Args:
        weather: Dictionary containing weather data with keys for air_temp (Celsius),
                 relative_humidity, wind_speed (mph), wind_gust (mph), and soil_moisture_15cm.
        manual_overrides: Optional dictionary where keys are metric names
                          (e.g., "temperature" in F, "humidity") and values are the
                          overridden numerical values.

    Returns:
        Tuple of (risk_level, explanation, effective_weather_values)
        where risk_level is "Red" or "Orange", and effective_weather_values
        contains the values used for calculation, with temperature in Fahrenheit.
    """
```

## Function Design

**Size:** Functions range from 20-150 lines depending on complexity
- Small helper functions: `validate_token_format()`, `format_age_string()` (< 30 lines)
- Medium business logic: `process_synoptic_data()`, `calculate_fire_risk()` (50-100 lines)
- Larger orchestration: `refresh_data_cache()` (100+ lines for complex async handling)

**Parameters:**
- Use type hints on all function parameters
- Keep parameter count reasonable (max 4-5 for regular functions)
- Use **kwargs for optional parameters in API endpoints
- Optional parameters have defaults and are documented

**Return Values:**
- Single return type or Tuple for multiple related values
- None for operations without meaningful return (side effects)
- Tuple pattern for multiple values: `Tuple[str, str]` or `Tuple[Optional[float], Optional[float], ...]`
- Status indicators returned from refresh operations: `Boolean or Tuple`

**Example from `endpoints.py`:**
```python
@router.get("/fire-risk")
async def fire_risk(
    request: Request,
    background_tasks: BackgroundTasks,
    wait_for_fresh: bool = False,
    session_token: Optional[str] = Cookie(None)
):
    """API endpoint to fetch fire risk status."""
```

## Module Design

**Exports:**
- Each module exports specific functions and classes
- Clear separation of concerns: `endpoints.py` for routes, `cache.py` for caching, `api_clients.py` for API calls
- Database/ORM: Uses SQLAlchemy in `subscriber_service.py` for subscriber management

**Barrel Files:**
- No barrel files (index.js/index.py) detected
- Direct imports from specific modules

**Class Design:**
- Single global instance pattern: `data_cache = DataCache()` in `cache.py`
- Classes encapsulate related state and methods: `DataCache` class in `cache.py`
- Thread-safe using locks: `self._lock = threading.Lock()` in `DataCache`

**Example class structure from `cache.py`:**
```python
class DataCache:
    DEFAULT_VALUES = {
        "temperature": 15.0,
        "humidity": 40.0,
        ...
    }

    def __init__(self):
        self.synoptic_data: Optional[Dict[str, Any]] = None
        self._lock = threading.Lock()
        self._update_complete_event = asyncio.Event()

    def update_cache(self, synoptic_data, fire_risk_data):
        # Implementation with lock
```

---

*Convention analysis: 2026-01-21*

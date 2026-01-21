# Testing Patterns

**Analysis Date:** 2026-01-21

## Test Framework

**Runner:**
- pytest 8.2.0+
- Config: `/Users/david/Documents/Coding/dev/fire-risk-dashboard/pytest.ini`

**Configuration (pytest.ini):**
```ini
[pytest]
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
asyncio_default_test_loop_scope = function
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    asyncio: mark a test as an asyncio test
    ui: mark a test as a UI test
    api: mark a test as an API test
    cache: mark a test as a cache test
    integration: mark a test as an integration test
    unit: mark a test as a unit test
```

**Assertion Library:**
- Built-in pytest assertions: `assert`, `assert x == y`, `assert "text" in result`

**Run Commands:**
```bash
pytest                          # Run all tests
pytest -v                       # Verbose output
pytest tests/test_*.py          # Run specific test files
pytest -k "test_name"          # Run tests matching name pattern
pytest --asyncio-mode=auto     # Run async tests
pytest --cov=.                 # Coverage report
```

**Key Dependencies (from requirements-dev.txt):**
- pytest>=8.2.0
- pytest-asyncio==0.26.0
- pytest-cov==4.1.0
- beautifulsoup4==4.12.2
- httpx==0.27.0
- pytest-playwright

## Test File Organization

**Location:**
- Co-located in `tests/` directory at project root
- Separate from source code in `tests/` subdirectory

**Naming:**
- `test_*.py` pattern: `test_fire_risk_logic.py`, `test_endpoints.py`, `test_cache_system.py`
- Test functions named `test_*`: `test_calculate_fire_risk_all_thresholds_exceeded`, `test_fire_risk_initial_fetch`
- Test classes named `Test*` (though rarely used, pattern exists in pytest.ini)

**Directory Structure:**
```
tests/
├── conftest.py                              # Shared fixtures and setup
├── test_endpoints.py                        # Endpoint tests
├── test_fire_risk_logic.py                  # Business logic tests
├── test_email_service.py                    # Email functionality tests
├── test_cache_system.py                     # Cache tests
├── test_integration.py                      # Integration tests
├── test_e2e.py                              # End-to-end tests
├── test_data_processing.py                  # Data processing tests
├── test_subscriber_service.py               # Subscriber functionality tests
└── ... (30 test files total)
```

## Test Structure

**Suite Organization:**

Test files are organized by module/feature being tested. Each test file imports the modules under test and uses fixtures from `conftest.py`.

**Example from `test_fire_risk_logic.py`:**
```python
import pytest
from fire_risk_logic import calculate_fire_risk
import unittest.mock

def test_calculate_fire_risk_all_thresholds_exceeded():
    weather_data = {
        "air_temp": 28,
        "relative_humidity": 10,
        "wind_speed": 20,
        "wind_gust": 25,
        "soil_moisture_15cm": 5
    }
    risk, explanation = calculate_fire_risk(weather_data)
    assert risk == "Red"
    assert "High fire risk" in explanation
```

**Setup/Teardown Patterns:**

Using pytest fixtures for setup/teardown. Functions use `yield` for teardown:

**From `conftest.py`:**
```python
@pytest.fixture
def reset_cache():
    """Reset the data cache before and after each test."""
    # Store original cache state
    original_cache = {
        "synoptic_data": data_cache.synoptic_data,
        "wunderground_data": data_cache.wunderground_data,
        "fire_risk_data": data_cache.fire_risk_data,
        "last_updated": data_cache.last_updated,
        ...
    }

    # Reset cache for test
    data_cache.synoptic_data = None
    data_cache.wunderground_data = None
    data_cache.fire_risk_data = None
    ...

    yield  # Test runs here

    # Restore original cache state
    data_cache.synoptic_data = original_cache["synoptic_data"]
    ...
```

**Test Data Setup:**

Mock data fixtures defined in `conftest.py` for reuse across tests:

```python
@pytest.fixture
def mock_synoptic_response():
    """Return a mock Synoptic API response."""
    return {
        "STATION": [
            {
                "STID": "SEYC1",
                "OBSERVATIONS": {
                    "air_temp_value_1": {"value": 0.5},
                    "relative_humidity_value_1": {"value": 98.0},
                    "wind_speed_value_1": {"value": 0.0}
                }
            },
            ...
        ]
    }
```

## Mocking

**Framework:** `unittest.mock` (built-in Python)

**Primary modules used:**
- `patch` - Replace function/module behavior
- `MagicMock` - Create mock objects
- `AsyncMock` - Create async mock functions
- `Mock` - Simple mock objects

**Patterns:**

Basic function mocking:
```python
from unittest.mock import patch

with patch('module.function', return_value=expected_value):
    # Code under test runs here
    result = function_being_tested()
```

Async function mocking:
```python
from unittest.mock import AsyncMock

mock_refresh = AsyncMock()
mock_refresh.return_value = True

with patch('endpoints.refresh_data_cache', mock_refresh):
    response = await client.get("/fire-risk")
    mock_refresh.assert_awaited_once()
```

Side effects for complex behavior:
```python
def refresh_side_effect(*args, **kwargs):
    data_cache.fire_risk_data = mock_data
    return True

mock_refresh.side_effect = refresh_side_effect
```

Mocking with autouse fixtures:
```python
@pytest.fixture(autouse=True)
def mock_ses_client_fixture():
    """Automatically mock the ses_client for all tests in this module."""
    with patch('email_service.ses_client', new_callable=MagicMock) as mock_client:
        mock_client.send_email.return_value = {'MessageId': 'test-id'}
        yield mock_client
```

**What to Mock:**
- External API calls (Synoptic, Weather Underground)
- Database operations
- Email services (AWS SES)
- Time-dependent functions (use freeze_gun or fixtures)
- Async operations that would block tests

**What NOT to Mock:**
- Core business logic (e.g., `calculate_fire_risk()` - test the actual logic)
- Data processing functions (test with real data structures)
- Cache operations in unit tests (use real DataCache with reset_cache fixture)

## Fixtures and Factories

**Test Data:**

Fixtures provide standardized test data structures. Key fixtures in `conftest.py`:

```python
@pytest.fixture
def mock_synoptic_response():
    # Returns standardized weather API response

@pytest.fixture
def mock_wunderground_response():
    # Returns wind gust API response

@pytest.fixture
def populate_cache_with_valid_data(mock_synoptic_response, mock_wunderground_response):
    """Populate the cache with valid data for integration tests."""
    weather_data = {
        "air_temp": 0.5,
        "relative_humidity": 98.0,
        "wind_speed": 0.0,
        "soil_moisture_15cm": 22.0,
        "wind_gust": 3.0,
        ...
    }
    risk, explanation = calculate_fire_risk(weather_data)
    fire_risk_data = {"risk": risk, "explanation": explanation, "weather": weather_data}
    data_cache.update_cache(mock_synoptic_response, fire_risk_data)
    return fire_risk_data
```

**Async Client Fixture:**

```python
@pytest.fixture(scope="function")
async def client():
    """Return an httpx.AsyncClient for the FastAPI app."""
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        yield client
```

**Event Loop Fixture:**

```python
@pytest.fixture(scope="function")
def event_loop():
    """Create an event loop for each test."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    if not loop.is_closed():
        loop.close()
```

**Location:**
- Fixtures defined in `tests/conftest.py` (50 lines to 245 lines)
- Shared across all test modules
- Module-specific fixtures can be defined in individual test files

## Coverage

**Requirements:** No explicit target enforced in codebase

**Current Coverage:**
- 30 test files with 300+ individual test functions
- Tests cover:
  - Unit tests for core logic (`test_fire_risk_logic.py`)
  - Endpoint tests for API (`test_endpoints.py`)
  - Cache system tests (`test_cache_system.py`)
  - Email service tests (`test_email_service.py`)
  - Integration tests (`test_integration.py`)
  - Data processing tests (`test_data_processing.py`)

**View Coverage:**
```bash
pytest --cov=. --cov-report=html  # Generate HTML coverage report
pytest --cov=. --cov-report=term  # Terminal coverage report
```

## Test Types

**Unit Tests:**
- Scope: Single function or method
- Approach: Test input/output with mocked dependencies
- Examples: `test_calculate_fire_risk_all_thresholds_exceeded`, `test_validate_token_format`
- Location: `test_fire_risk_logic.py`, `test_data_processing.py`

**Integration Tests:**
- Scope: Multiple components working together
- Approach: Mock only external services, test actual cache and logic
- Examples: `test_initial_cache_empty`, `test_fire_risk_stale_data`
- Location: `test_integration.py`, `test_endpoints.py`
- Pattern: Use real cache with `reset_cache` fixture, mock API calls

**E2E Tests:**
- Scope: Full flow from endpoint to response
- Approach: Start test server, make HTTP requests, verify responses
- Examples: Tests in `test_e2e.py`
- Framework: Using pytest with httpx for async HTTP client
- Pattern: Use `client` fixture for async HTTP calls

## Common Patterns

**Async Testing:**

All async tests use `@pytest.mark.asyncio` decorator:

```python
@pytest.mark.asyncio
async def test_fire_risk_initial_fetch(client):
    """Test the /fire-risk endpoint when the cache is initially empty."""
    mock_refresh = AsyncMock()
    mock_refresh.return_value = True

    with patch('endpoints.refresh_data_cache', mock_refresh):
        response = await client.get("/fire-risk")
        assert response.status_code == 200
        mock_refresh.assert_awaited_once()
```

Async fixtures use `async with` pattern:

```python
@pytest.fixture(scope="function")
async def client():
    """Return an httpx.AsyncClient for the FastAPI app."""
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        yield client
```

**Error Testing:**

Testing both success and failure paths:

```python
def test_calculate_fire_risk_missing_data():
    """Test that missing data is handled gracefully."""
    weather_data = {
        "air_temp": 28,
        "relative_humidity": 10,
        "wind_speed": 20
        # Missing wind_gust and soil_moisture
    }
    risk, explanation = calculate_fire_risk(weather_data)
    assert risk == "Orange"  # Should handle gracefully
    assert "Low or Moderate Fire Risk" in explanation

def test_calculate_fire_risk_invalid_data():
    """Test that invalid data types are caught."""
    weather_data = {
        "air_temp": "high",  # Invalid - should be float
        "relative_humidity": 10,
        "wind_speed": 20,
        "wind_gust": 25,
        "soil_moisture_15cm": 5
    }
    risk, explanation = calculate_fire_risk(weather_data)
    assert risk == "Error"
    assert "Could not calculate risk" in explanation
```

Testing exception handling with mocks:

```python
def test_calculate_fire_risk_exception_handling():
    """Test that exceptions during calculation are handled."""
    weather_data = {...}

    with unittest.mock.patch('fire_risk_logic.logger.info') as mock_logger:
        mock_logger.side_effect = Exception("Mock logger error")
        risk, explanation = calculate_fire_risk(weather_data)
        assert risk == "Error"
        assert "Could not calculate risk" in explanation
```

**Cache Testing Pattern:**

```python
def test_is_stale_old_data(cache):
    """Test that cache detects stale data correctly."""
    cache.last_updated = datetime.now(TIMEZONE) - timedelta(minutes=30)
    assert cache.is_stale() is True

def test_update_cache(cache):
    """Test cache update stores data correctly."""
    synoptic_data = {"test": "synoptic"}
    fire_risk_data = {"risk": "low"}

    cache.update_cache(synoptic_data, fire_risk_data)

    assert cache.synoptic_data == synoptic_data
    assert cache.fire_risk_data == fire_risk_data
    assert cache.last_updated is not None
    assert cache.last_update_success is True
```

**Parametrized Tests (Not Used):**
- No `@pytest.mark.parametrize` decorators found
- Tests use individual test functions instead of parametrization
- Could benefit from parametrization for threshold testing

---

*Testing analysis: 2026-01-21*

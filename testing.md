# Fire Risk Dashboard Testing Guide

This document provides guidelines for running tests and maintaining test coverage for the Fire Risk Dashboard application.

## Test Structure

Tests are organized in the `tests/` directory with the following structure:

- `conftest.py` - Contains shared fixtures and test setup
- `test_api_clients.py` - Tests for API client functionality
- `test_cache_system.py` - Tests for the data caching mechanism
- `test_endpoints.py` - Tests for API endpoints
- `test_ui_rendering.py` - Tests for UI rendering

## Running Tests

### Prerequisites

Ensure you have the development dependencies installed:

```bash
pip install -r requirements-dev.txt
```

### Basic Test Execution

To run the complete test suite:

```bash
pytest
```

For more detailed output, use the verbose flag:

```bash
pytest -v
```

### Running with Coverage

To run tests with coverage reporting to the terminal:

```bash
pytest --cov=. --cov-report=term
```

To generate an XML coverage report:

```bash
pytest --cov=. --cov-report=xml
```

### Running Specific Tests

Run tests from a specific file:

```bash
pytest tests/test_api_clients.py
```

Run a specific test function:

```bash
pytest tests/test_api_clients.py::test_get_api_token
```

## Test Types

The project uses pytest markers to categorize tests. The markers are defined in `pytest.ini`:

| Marker | Description |
|--------|-------------|
| `asyncio` | Tests that use asyncio functionality |
| `ui` | Tests for UI components and rendering |
| `api` | Tests for API endpoints and functionality |
| `cache` | Tests for the caching system |
| `integration` | Tests that verify interactions between components |
| `unit` | Tests that verify individual component functionality |

To run tests with a specific marker:

```bash
# Run only API tests
pytest -m api

# Run only UI tests
pytest -m ui

# Run only cache tests
pytest -m cache

# Run only unit tests (not integration)
pytest -m unit

# Run only integration tests
pytest -m integration
```

## When to Run Tests in Your Development Cycle

### 1. Before Starting New Work

Run the full test suite before starting new development to ensure you're beginning with a clean state:

```bash
pytest --cov=.
```

### 2. During Development (Continuous Testing)

While actively coding, run specific tests related to the component you're working on:

```bash
# If working on API clients
pytest tests/test_api_clients.py -v

# If working on a specific function
pytest tests/test_api_clients.py::test_get_api_token -v
```

### 3. After Completing a Feature or Fix

Run the full test suite with coverage to ensure your changes don't break existing functionality and maintain good coverage:

```bash
pytest --cov=. --cov-report=term
```

### 4. Before Committing Code

Always run the full test suite before committing:

```bash
pytest
```

### 5. Before Merging or Deploying

Run comprehensive tests including coverage:

```bash
pytest --cov=. --cov-report=xml
```

### 6. After Refactoring

When refactoring code without changing functionality, run tests to ensure behavior remains the same:

```bash
pytest
```

## Coverage Reporting

The project currently has approximately 61% line coverage. Coverage reports can help identify untested code paths and prioritize where to add new tests.

To view detailed coverage information:

```bash
# Generate and view HTML coverage report
pytest --cov=. --cov-report=html
# Then open htmlcov/index.html in a browser

# Or for terminal output
pytest --cov=. --cov-report=term-missing
```

## Best Practices

1. **Write Tests First**: For new features, consider writing tests before implementation (Test-Driven Development)

2. **Test in Isolation**: When working on a specific component, run its tests frequently

3. **Regular Full Suite Runs**: Run the complete test suite at least daily

4. **Maintain Coverage**: Aim to maintain or improve coverage percentage (target: 80%+)

5. **Add Missing Tests**: When fixing bugs, add tests that would have caught the bug

6. **Test Edge Cases**: Especially for the cache system and API clients, test failure scenarios

7. **Integration Testing**: Periodically run integration tests to ensure components work together

## Current Test Coverage Gaps

The current test suite has several gaps that should be addressed:

1. **Incomplete Module Coverage**:
   - `fire_risk_logic.py` lacks dedicated tests
   - `data_processing.py` is insufficiently tested
   - `dev_endpoints.py` has no tests

2. **Limited Code Path Coverage**:
   - Many conditional branches remain untested
   - Error handling paths are often missing tests

3. **Missing Test Types**:
   - Limited integration testing between components
   - Insufficient edge case testing

> **Note**: These coverage gaps are referenced in the project roadmap (see roadmap.md Phase 3: Testing Strategy Implementation) and will be addressed as part of the planned testing improvements.

## Setting Up Automated Testing

Consider setting up pre-commit hooks to run tests automatically:

```bash
# Example pre-commit hook script
pytest tests/test_api_clients.py tests/test_cache_system.py
```

For more comprehensive CI/CD, you could use GitHub Actions or similar to run the full test suite on every push.

## Future Test Improvements

To improve test coverage and quality, consider:

1. Creating dedicated test files for untested modules:
   - `test_fire_risk_logic.py`
   - `test_data_processing.py`
   - `test_dev_endpoints.py`

2. Adding more tests for error conditions and exception handling

3. Implementing end-to-end tests that verify the full data flow

4. Setting coverage thresholds and enforcing them in CI/CD

# Fix for API Client Import Error

## Original Issue

The GitHub CI build was failing with the following error:

```
ImportError while importing test module '/home/runner/work/fire-risk-dashboard/fire-risk-dashboard/tests/test_api_clients.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/hostedtoolcache/Python/3.9.21/x64/lib/python3.9/importlib/__init__.py:127: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
tests/test_api_clients.py:5: in <module>
    from main import get_api_token, get_weather_data, get_wunderground_data
E   ImportError: cannot import name 'get_api_token' from 'main' (/home/runner/work/fire-risk-dashboard/fire-risk-dashboard/main.py)
```

## Root Cause

The test file `tests/test_api_clients.py` was trying to import three API client functions that were missing from `main.py`:
- `get_api_token`
- `get_weather_data`
- `get_wunderground_data`

These functions were present in `old-main.py` but not in the current `main.py` file.

## Solution

1. Add the three missing API client functions from `old-main.py` to `main.py` at the module level so they can be imported by the tests.
2. Verify that the specific failing test (`test_api_clients.py`) passes.

## Implementation

The three functions were added to `main.py` using the `replace_in_file` tool. After adding these functions, the specific API client tests started passing:

```
tests/test_api_clients.py::test_get_api_token PASSED
tests/test_api_clients.py::test_get_api_token_failure PASSED
tests/test_api_clients.py::test_get_weather_data PASSED
tests/test_api_clients.py::test_get_weather_data_failure PASSED
tests/test_api_clients.py::test_get_weather_data_retry PASSED
tests/test_api_clients.py::test_get_wunderground_data PASSED
tests/test_api_clients.py::test_get_wunderground_data_failure PASSED
tests/test_api_clients.py::test_get_wunderground_data_empty_response PASSED
```

## Additional Notes

While other tests in the test suite are still failing with 404 Not Found errors, these are unrelated to the original issue and should be addressed separately if needed.

The focus of this fix was specifically on resolving the ImportError in the API client tests, which has been successfully addressed.

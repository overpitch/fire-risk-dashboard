# Debugging Guide: API Response Logging

## Key Principle: Toggleable Debug Logging

When adding debug logging, ALWAYS follow these guidelines to ensure logs can be easily disabled:

### 1. Use Environment-Controlled Debug Flags

All debug logging should be controlled by dedicated debug flags defined in `config.py`:

```python
# Debug flags - set to False by default for production
DEBUG_API_RESPONSES = os.getenv("DEBUG_API_RESPONSES", "False").lower() == "true"
DEBUG_CACHE_OPERATIONS = os.getenv("DEBUG_CACHE_OPERATIONS", "False").lower() == "true"
# Add other debug flags as needed for different components
```

### 2. Wrap All Debug Logs in Conditional Blocks

ALWAYS wrap debug logging in conditional checks:

```python
if DEBUG_API_RESPONSES:
    logger.debug(f"🔍 API Response Structure: {json.dumps(data, default=str)[:500]}...")
```

### 3. Use Different Log Levels Appropriately

- `logger.debug()`: For detailed debugging info (controlled by debug flags)
- `logger.info()`: For standard operational information
- `logger.warning()`: For concerning but non-critical issues
- `logger.error()`: For errors that impact functionality

### 4. Format Debug Output Consistently

For API responses and complex objects:
- Use emoji prefixes for visual scanning (🔍, 🚨, etc.)
- Truncate large objects (e.g., `[:500]`)
- Include key structural information (e.g., `list(data.keys())`)

### 5. Enabling Debug Logs

To enable debug logging during development:
- Set environment variable: `export DEBUG_API_RESPONSES=true`
- Or update the `.env` file with `DEBUG_API_RESPONSES=true`
- Restart the application to apply changes

### 6. Production Environments

- All debug flags default to `False` for production
- Debug output can be enabled temporarily in production if needed
- No code changes are required to disable debug output

## Example Implementation

```python
# In api_clients.py
def get_weather_data(location_ids):
    # Regular operational logging
    logger.info(f"🔍 Requesting weather data for stations: {location_ids}")
    
    response = requests.get(request_url)
    data = response.json()
    
    # Conditional debug logging
    if DEBUG_API_RESPONSES:
        logger.debug(f"🔍 API Response Structure: {list(data.keys())}")
        logger.debug(f"🔍 API Response Sample: {json.dumps(data, default=str)[:500]}...")
    
    # Validation with conditional debug info
    if "STATION" not in data:
        # Regular error log everyone sees
        logger.error("Weather API response missing STATION data")
        
        # Detailed debug info only shown when debugging
        if DEBUG_API_RESPONSES:
            logger.debug(f"🚨 Response Keys: {list(data.keys())}")
            logger.debug(f"🚨 Response Content Type: {type(data)}")
            if "error" in data:
                logger.debug(f"🚨 API Error Message: {data.get('error')}")
```

## Troubleshooting the "Weather API response missing STATION data" Error

This specific error occurs in the `process_synoptic_data` function when the Synoptic API response doesn't contain the expected "STATION" key. To debug this issue:

1. **Enable detailed API response logging**:
   ```
   export DEBUG_API_RESPONSES=true
   ```

2. **Restart the application** to apply the debug flag.

3. **Check the logs** for detailed information about:
   - The API response structure
   - Available keys in the response
   - Error messages or summaries from the API

4. **Common causes**:
   - API authentication issues (invalid/expired token)
   - API response format changes
   - Network or service issues
   - Request parameter errors

5. **Fix verification**:
   Once you believe you've fixed the issue, disable the debug logging:
   ```
   export DEBUG_API_RESPONSES=false
   ```
   or remove the environment variable altogether.

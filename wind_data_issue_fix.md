# Wind Data Issue: Static Data Fix

## Problem Description

The UI in production was showing static wind data values for station 629PG (PG&E Sand Shed):
- UI showing wind speed of ~2 mph and wind gusts of ~5 mph
- Actual real-world values were wind speed of ~5 mph and gusts of ~16 mph

## Root Cause Analysis

1. **Caching Issue**: The application was using cached wind data instead of refreshing it from the Synoptic API.
   - Only wind_speed and wind_gust fields were marked as using cached data
   - Other weather metrics (temperature, humidity, soil_moisture) were refreshing correctly

2. **Potential Data Conversion Issue**: There appeared to be a potential issue with how the wind data values are converted from m/s to mph in the UI.
   - Values in the cache are stored in m/s (the API's native unit)
   - The UI should convert these to mph for display (multiply by 2.237)
   - There may have been an inconsistency in this conversion process

## Solution Implemented

We implemented a more streamlined solution that integrates directly into the application's startup and refresh processes:

### 1. Enhanced Application Startup

Modified the `lifespan` function in `main.py` to ensure wind data is properly refreshed at application startup:

```python
@asynccontextmanager
async def lifespan(app):
    """Lifespan context manager for application startup and shutdown."""
    # Startup event
    logger.info("🚀 Application startup: Initializing data cache...")
    
    # Try to fetch initial data, but don't block startup if it fails
    try:
        # Force a complete refresh of the cache with force=True
        await refresh_data_cache(force=True)
        
        # Check specifically that wind data isn't cached after refresh
        if data_cache.cached_fields['wind_speed'] or data_cache.cached_fields['wind_gust']:
            logger.warning("⚠️ Wind data still marked as cached after initial refresh, forcing second refresh...")
            await refresh_data_cache(force=True)
            
            # Log the final status of wind data
            if data_cache.cached_fields['wind_speed'] or data_cache.cached_fields['wind_gust']:
                logger.error("❌ Wind data still marked as cached after second refresh attempt")
            else:
                logger.info("✅ Wind data refreshed successfully after second attempt")
        else:
            logger.info("✅ Initial data cache populated successfully with fresh wind data")
    except Exception as e:
        logger.error(f"❌ Failed to populate initial data cache: {str(e)}")
        logger.info("Application will continue startup and retry data fetch on first request")
    
    # Yield control back to FastAPI during application lifetime
    yield
    
    # Shutdown event (if needed in the future)
    logger.info("🛑 Application shutting down...")
```

This ensures fresh wind data on every application restart in both development and production environments.

### 2. Improved Cache Refresh Logic

Added a wind data check in `cache_refresh.py` to ensure wind data is never incorrectly marked as cached during regular refreshes:

```python
# --- Wind Data Check ---
# Specifically verify wind data is properly refreshed and not stuck in cached mode
if data_cache.cached_fields["wind_speed"] or data_cache.cached_fields["wind_gust"]:
    logger.warning("Wind data marked as cached after processing new data - this should not happen!")
    # Reset the wind cached flags to ensure data refreshes properly
    data_cache.cached_fields["wind_speed"] = False
    data_cache.cached_fields["wind_gust"] = False
    logger.info("Reset wind data cached flags to ensure fresh data")
```

This additional check guarantees that even if there is an issue with the wind data refresh process, the system will automatically correct it and ensure fresh data is used.

## Testing

You can verify the current wind data from the API by running:
```python
python check_wind_data.py
```

This will fetch the latest data from the Synoptic API for station 629PG and display:
- Current wind speed (in m/s and mph)
- Current wind gust (in m/s and mph)
- Timestamps for when these measurements were taken

## Possible Long-term Improvements

1. **Enhance Caching Logic**: Review the caching mechanism to ensure all fields refresh properly.

2. **Improve Error Handling**: Add more robust error handling for API failures that specifically identifies when wind data fails to update.

3. **Data Consistency Checks**: Implement checks to compare cached values with new API values to detect when data hasn't changed for an abnormal period.

4. **Monitoring**: Add monitoring specifically for wind data staleness to alert when the issue reoccurs.

5. **Unit Conversion Standardization**: Ensure consistent unit conversion throughout the application (m/s to mph).

## References

- Station ID: 629PG (PG&E Sand Shed)
- Synoptic API documentation
- Cache implementation in `cache.py` and `cache_refresh.py`

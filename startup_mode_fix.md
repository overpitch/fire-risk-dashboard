# App Startup Mode Fix

## Issue Summary

The fire risk dashboard was defaulting to "Test Mode" upon fresh deployments to production (Render). This would cause the following issues:

1. Weather data would appear to be stale, showing timestamps like "(1 minute old)"
2. Users would have to manually disable test mode through the admin panel after each deployment
3. The app would not automatically fetch fresh data from the APIs until test mode was disabled

## Root Cause

After investigation, we found that the cache initialization logic was setting the app to start in "Test Mode" (cached data mode) when no disk cache was available - which is always the case for fresh deployments.

Specifically in `cache.py`, when initializing without a disk cache or with invalid disk cache data:

```python
# If no valid data found, initialize same as fresh cache
self.cached_fields = {field: True for field in ["temperature", "humidity", "wind_speed", "soil_moisture", "wind_gust"]}
self.using_cached_data = True  # Start with using defaults as there's no valid data
```

## Solution

The fix modifies two key parts of the initialization logic in `cache.py`:

1. **Fresh initialization** (no disk cache):
   - Changed `self.using_cached_data` to `False` to start in normal mode
   - Set all fields in `cached_fields` to `False` to not mark anything as cached
   - Added detailed logging to indicate starting in normal mode

2. **Disk cache loading**:
   - Modified to ALWAYS start in normal mode regardless of disk cache state
   - Added clear logging about the startup state
   - Preserved the ability to use cached values as fallbacks if API calls fail

Example of the fixed initialization code:

```python
# Initialize cache fields flags - mark as NOT cached to force API data fetch
self.cached_fields = {field: False for field in ["temperature", "humidity", "wind_speed", "soil_moisture", "wind_gust"]}
# IMPORTANT: Set to FALSE by default - do not start in test mode
self.using_cached_data = False  # Start in normal mode, not test mode
self.using_default_values = True  # Still track that we're using defaults
            
logger.info("⚠️ New deployment detected - starting in NORMAL mode (not test mode)")
```

## Benefits

1. The application will now always start in normal mode after deployment
2. It will immediately attempt to fetch fresh data from APIs
3. Admin users no longer need to manually disable test mode after deployments
4. The system still maintains fall-back values if API calls fail

## Testing

To verify the fix:
1. Deploy to production (Render)
2. Confirm the app starts in normal mode, showing fresh data with no "X minutes old" indicators
3. Check server logs for the new message: "⚠️ New deployment detected - starting in NORMAL mode (not test mode)"
4. Test mode can still be manually enabled if needed for testing

## Note for Future Development

This change ensures a better production experience while maintaining the ability to use test mode when explicitly enabled through the admin panel. The system will now have a more predictable startup behavior.

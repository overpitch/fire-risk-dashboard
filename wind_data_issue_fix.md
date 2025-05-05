k# Wind Data Issue Fix

## Issue Summary

The fire risk dashboard was showing stale wind data in production (Render) environment, even though the code was the same as in the development environment. Specifically:

1. In production, the wind data (and other data types) were marked as "(6 minutes old)"
2. Wind speed and wind gust values were incorrect or stale
3. The issue appeared after the latest code push to production

## Root Cause

After investigation, we found that the cache system was not properly preserving the state of which fields were using cached data during cache updates. This was due to a code change where the following lines were commented out in the `update_cache()` method in `cache.py`:

```python
# Restore the cached_fields and using_cached_data state # REMOVED
# self.cached_fields = cached_fields_state # REMOVED
# self.using_cached_data = using_cached_data_state # REMOVED
```

Without these lines, the system wasn't properly tracking which fields were using cached values, resulting in:

1. The system thinking it had fresh data when it didn't
2. No indication in the UI that data was stale
3. Failure to refresh data when needed

## Solution

After careful analysis, we found that the original problem stemmed from commented-out code that was responsible for tracking cached fields. However, we needed a more sophisticated solution than simply restoring the code, as there appeared to be reasons it was commented out in the first place.

Our solution involved three main improvements:

1. Improved state tracking in the `update_cache()` method:
   ```python
   # Save the current cached fields state before updating
   cached_fields_state = self.cached_fields.copy()
   using_cached_data_state = self.using_cached_data
   
   # ... later in the method ...
   
   # MODIFIED CACHE STATE HANDLING:
   # First, check wind data - ensure it's correctly marked as cached/non-cached
   if "weather" in fire_risk_data:
       weather = fire_risk_data.get("weather", {})
       
       # Check if wind_speed is present in the fresh data
       if weather.get("wind_speed") is not None:
           cached_fields_state["wind_speed"] = False
       else:
           # If wind_speed is None, it should be marked as cached
           cached_fields_state["wind_speed"] = True
           
       # Check if wind_gust is present in the fresh data
       if weather.get("wind_gust") is not None:
           # Check if the wind_gust is actually from cache
           wind_gust_stations = weather.get("wind_gust_stations", {})
           for station in wind_gust_stations.values():
               if station.get("is_cached", False):
                   cached_fields_state["wind_gust"] = True
                   break
           else:
               # If no station is cached, mark as not cached
               cached_fields_state["wind_gust"] = False
       else:
           # If wind_gust is None, it should be marked as cached
           cached_fields_state["wind_gust"] = True
   
   # Now restore the cached_fields and using_cached_data state
   self.cached_fields = cached_fields_state
   # Recalculate using_cached_data based on actual field states
   self.using_cached_data = any(self.cached_fields.values())
   ```

2. Enhancing the `get_field_value()` method to better handle cached wind_gust data:
   ```python
   # Check if the value is from cache (for wind_gust specifically)
   is_cached = False
   if field_name == "wind_gust" and "wind_gust_stations" in self.fire_risk_data["weather"]:
       # Check if any station has cached data
       for station_data in self.fire_risk_data["weather"]["wind_gust_stations"].values():
           if station_data.get("is_cached", False):
               is_cached = True
               break
   
   # Only update the cached flag if it's not a cached value
   if not is_cached:
       # Reset cached flag for this field since we're using direct value
       self.cached_fields[field_name] = False
       
       # Check if any field is still using cached data
       self.using_cached_data = any(self.cached_fields.values())
   ```

3. Adding detailed logging to monitor cache state:
   ```python
   # Log cache state for monitoring
   logger.info(f"Cache state after update: using_cached_data={self.using_cached_data}")
   logger.info(f"Cached fields: {', '.join([f for f, v in self.cached_fields.items() if v])}")
   ```

## Verification

Two verification scripts were created to test the fix:

1. `test_cache_fix.py` - A simple test that simulates updating the cache with missing wind data, then complete data, then missing data again.
2. `verify_fixed_wind_data.py` - A more comprehensive test that fetches real data from the Synoptic API and verifies the whole workflow.

Both tests confirmed that:
- The cache system now correctly tracks which fields are using cached data
- When data is missing from the API, the system properly falls back to cached values
- The cache state is properly preserved during updates

## Deployment Notes

When deploying this fix to production:

1. Ensure the fix is applied to the `cache.py` file
2. Restart the application to ensure the changes take effect
3. Monitor the logs for any "Cache state after update" entries to verify the fix is working
4. Check the dashboard UI to confirm that wind data is updating correctly
5. If data is still stale, check if the API is returning valid data

## Future Considerations

To prevent similar issues in the future:

1. Add automated tests that verify cache behavior
2. Consider adding more explicit UI indicators when data is stale
3. Implement a health check endpoint that verifies all data sources are working
4. Add monitoring alerts for when data sources have been stale for too long

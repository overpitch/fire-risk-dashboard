import asyncio
from cache_refresh import refresh_data_cache
from cache import data_cache

async def fix_wind_data_issue():
    """
    Fix the static wind data issue by forcing a complete cache refresh
    and checking that wind data is properly updated.
    """
    print("Current wind data in cache:")
    print(f"Wind Speed: {data_cache.get_field_value('wind_speed')} (should be in m/s)")
    print(f"Wind Gust: {data_cache.get_field_value('wind_gust')} (should be in m/s)")
    print(f"Using cached data: {data_cache.using_cached_data}")
    print(f"Cached fields: {data_cache.cached_fields}")
    print("\nForcing a complete cache refresh...")
    
    # Force a complete refresh of the cache
    success = await refresh_data_cache(force=True)
    
    print(f"\nCache refresh {'successful' if success else 'failed'}")
    print("\nAfter refresh - wind data in cache:")
    print(f"Wind Speed: {data_cache.get_field_value('wind_speed')} (should be in m/s)")
    print(f"Wind Gust: {data_cache.get_field_value('wind_gust')} (should be in m/s)")
    print(f"Using cached data: {data_cache.using_cached_data}")
    print(f"Cached fields: {data_cache.cached_fields}")
    
    # Verify the fix worked
    if not data_cache.cached_fields['wind_speed'] and not data_cache.cached_fields['wind_gust']:
        print("\n✅ Fix successful! Wind data is now refreshing properly.")
        print("The UI should now display current wind values from station 629PG.")
    else:
        print("\n❌ Problem still exists. Wind data is still marked as cached.")
        print("Additional troubleshooting needed.")

if __name__ == "__main__":
    asyncio.run(fix_wind_data_issue())

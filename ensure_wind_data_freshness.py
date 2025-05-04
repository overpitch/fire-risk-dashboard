#!/usr/bin/env python
"""
Script to ensure wind data freshness by performing a scheduled check and refresh.
This can be run as a cron job or scheduled task to periodically verify and fix 
wind data if it gets stuck in a cached state.
"""
import asyncio
import logging
import datetime
from cache_refresh import refresh_data_cache
from cache import data_cache

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='wind_data_refresh.log'
)
logger = logging.getLogger('wind_data_refresher')

async def check_and_refresh_wind_data():
    """
    Check if wind data is using cached values and force a refresh if needed.
    """
    current_time = datetime.datetime.now()
    logger.info(f"Running wind data freshness check at {current_time}")
    
    # Check if wind data is using cached values
    if data_cache.cached_fields['wind_speed'] or data_cache.cached_fields['wind_gust']:
        logger.warning(f"Wind data is using cached values. Current values: wind_speed={data_cache.get_field_value('wind_speed')}, wind_gust={data_cache.get_field_value('wind_gust')}")
        logger.info("Forcing refresh of cache to update wind data...")
        
        # Force a complete refresh of the cache
        success = await refresh_data_cache(force=True)
        
        if success:
            # Check if the refresh fixed the issue
            if not data_cache.cached_fields['wind_speed'] and not data_cache.cached_fields['wind_gust']:
                logger.info(f"✅ Refresh successful! Wind data is now fresh. New values: wind_speed={data_cache.get_field_value('wind_speed')}, wind_gust={data_cache.get_field_value('wind_gust')}")
            else:
                logger.error("❌ Wind data is still marked as cached after refresh. Further investigation needed.")
        else:
            logger.error("❌ Cache refresh failed. Could not update wind data.")
    else:
        logger.info(f"Wind data is already fresh. Current values: wind_speed={data_cache.get_field_value('wind_speed')}, wind_gust={data_cache.get_field_value('wind_gust')}")
    
    return True

if __name__ == "__main__":
    asyncio.run(check_and_refresh_wind_data())

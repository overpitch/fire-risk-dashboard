# 🔄 Cache System Simplification Implementation Plan

## Overview

This document outlines the technical implementation plan for simplifying the caching system in the Fire Risk Dashboard. The goal is to replace the current complex field-by-field caching mechanism with a simpler snapshot-based approach that improves reliability and user trust.

## Problem Statement

The current caching system is experiencing a critical issue where stale data is being displayed as if it were live data. A user reported seeing a wind speed of 3 mph on our dashboard when the actual current wind speed was 7 mph according to the weather station's own website. This undermines user trust in our dashboard.

The complexity of the current field-by-field caching system makes it difficult to debug and maintain. The current system tries to optimize freshness on a per-field basis, but this has led to confusing states where some data is fresh while other data is stale, without clear indicators to users.

## Proposed Solution

Replace the field-by-field caching with a simpler snapshot-based approach:

1. Store complete snapshots of weather data with a single timestamp
2. Always display the entire snapshot as a unit
3. Clearly indicate to users when they're viewing cached data
4. Maintain regular refresh attempts every 10 minutes

## Environment Setup

**⚠️ CRITICAL: ALWAYS ENSURE VIRTUAL ENVIRONMENT IS ACTIVE BEFORE EXECUTING COMMANDS ⚠️**

Before running any Python commands or installing any packages, ensure the virtual environment is active by checking for the `(venv)` prefix in your terminal prompt.

If the virtual environment is not active, activate it:

```bash
# On macOS/Linux
source venv/bin/activate

# On Windows
.\venv\Scripts\activate
```

Never run Python commands or install packages outside the project's virtual environment.

### Command Execution Checklist
- [ ] Virtual environment is active
- [ ] Working in the correct directory
- [ ] Required dependencies are installed

## Implementation Details

### 1. Refactor DataCache Class

#### Current Implementation
The current `DataCache` class in `cache.py` tracks individual fields with separate timestamps and cached flags:

```python
self.last_valid_data: Dict[str, Any] = {
    # Store each weather field individually with its own timestamp
    "fields": {
        "temperature": {"value": value, "timestamp": timestamp},
        "humidity": {"value": value, "timestamp": timestamp},
        # ... other fields
    },
    # Full API responses for backwards compatibility
    "synoptic_data": None,
    "wunderground_data": None,
    "fire_risk_data": None,
    "timestamp": timestamp,
}

# Track which fields are using cached data
self.cached_fields: Dict[str, bool] = {
    "temperature": True,
    "humidity": True,
    # ... other fields with flags
}
```

#### New Implementation
Simplify to store complete snapshots:

```python
self.snapshots: List[Dict[str, Any]] = [
    {
        "synoptic_data": data,
        "wunderground_data": data,
        "fire_risk_data": data,
        "timestamp": timestamp,
        "is_stale": False
    }
]
# Current active snapshot (most recent successful fetch)
self.current_snapshot: Dict[str, Any] = {}
# Flag to indicate if we're using cached data
self.using_cached_data: bool = False
```

### 2. Update Data Refresh Logic

#### Current Implementation
The `refresh_data_cache()` function in `cache_refresh.py` attempts to fetch data, combines partial results, and updates individual fields with their own timestamps. It refreshes at fixed 10-minute intervals regardless of when the source data is updated.

#### New Implementation
We've implemented a smarter approach with these key improvements:

1. **All-or-nothing Data Updates**: Instead of partial field updates, we only update when we have complete data

2. **Optimized Refresh Schedule**: Instead of fixed intervals, we schedule refreshes at :20, :40, and :00 past each hour to align with the SEYC1 weather station's update schedule (which updates at :00, :15, :30, and :45)

3. **Clear Indication of Data Freshness**: Users can always see if they're viewing fresh or cached data

Here's the core implementation:

```python
async def refresh_data_cache(background_tasks: Optional[BackgroundTasks] = None) -> bool:
    """Refresh data cache with an all-or-nothing approach"""
    # Reset the update complete event
    data_cache.reset_update_event()
    
    # Acquire update lock
    data_cache.update_in_progress = True
    logger.info("Starting data cache refresh...")
    
    success = False
    
    try:
        # Fetch data from both APIs concurrently
        weather_data, wunderground_data = await fetch_all_data()
        
        # Only update cache if both API calls succeeded
        if weather_data is not None and wunderground_data is not None:
            # Process the API responses to get complete weather data
            latest_weather = combine_weather_data(weather_data, wunderground_data)
            
            # Calculate fire risk based on the latest weather data
            risk, explanation = calculate_fire_risk(latest_weather)
            
            # Create the fire risk data
            fire_risk_data = {
                "risk": risk, 
                "explanation": explanation, 
                "weather": latest_weather,
                "timestamp": datetime.now(TIMEZONE).isoformat(),
                "is_fresh": True
            }
            
            # Update the cache with new complete snapshot
            data_cache.update_cache(weather_data, wunderground_data, fire_risk_data)
            success = True
            logger.info("Complete snapshot cache refresh successful")
        else:
            # Log which APIs failed
            if weather_data is None:
                logger.error("Failed to fetch data from Synoptic API")
            if wunderground_data is None:
                logger.error("Failed to fetch data from Weather Underground API")
            
            # If we have any previous snapshot, mark it as stale but keep using it
            if data_cache.current_snapshot:
                data_cache.using_cached_data = True
                logger.info("Using previous snapshot as fallback")
                
            success = False
    except Exception as e:
        logger.error(f"Error refreshing data cache: {str(e)}")
        success = False
    
    # Update state
    data_cache.update_in_progress = False
    data_cache.last_update_success = success
    
    # Schedule next refresh at optimal time based on SEYC1 update schedule
    if background_tasks:
        background_tasks.add_task(schedule_next_refresh)
        
    return success
```

#### Smart Refresh Scheduling

The system calculates the optimal time for the next refresh to align with SEYC1 weather station updates:

```python
def get_next_refresh_delay() -> int:
    """Calculate minutes until next scheduled refresh at :20, :40, or :00.
    
    The SEYC1 weather station updates on the quarter-hour (:00, :15, :30, :45),
    so we fetch at :20, :40, and :00 to get data ~5 minutes after it updates.
    """
    now = datetime.now(TIMEZONE)
    current_minute = now.minute
    
    # Calculate minutes until next scheduled refresh
    if current_minute < 20:
        return 20 - current_minute     # Wait until XX:20
    elif current_minute < 40:
        return 40 - current_minute     # Wait until XX:40
    else:
        return 60 - current_minute     # Wait until the next hour's XX:00
```

This approach ensures we fetch fresh data approximately 5 minutes after the weather station updates it, maximizing the freshness of our data while minimizing unnecessary API calls.

### 3. Simplify Cache Update Method

#### Current Implementation
`update_cache()` in `cache.py` has complex logic to update individual field values and track which fields are using cached data.

#### New Implementation
Simplify to store complete snapshots:

```python
def update_cache(self, synoptic_data, wunderground_data, fire_risk_data):
    """Update the cache with a new complete snapshot"""
    # Create timezone-aware datetime
    current_time = datetime.now(TIMEZONE)
    
    with self._lock:
        # Store the complete snapshot
        new_snapshot = {
            "synoptic_data": synoptic_data,
            "wunderground_data": wunderground_data,
            "fire_risk_data": fire_risk_data,
            "timestamp": current_time,
            "is_stale": False
        }
        
        # Add to snapshots list (limit to last 24 snapshots to manage memory)
        self.snapshots.append(new_snapshot)
        if len(self.snapshots) > 24:  # Keep last 24 (4 hours at 10-min intervals)
            self.snapshots.pop(0)
            
        # Set as current snapshot
        self.current_snapshot = new_snapshot
        self.last_updated = current_time
        self.last_update_success = True
        self.using_cached_data = False
        
        # Save cache to disk
        self._save_cache_to_disk()
        
        # Log cache update
        logger.info(f"Complete snapshot cached at {current_time}")
```

### 4. Update API Endpoints

#### Current Implementation
The `/fire-risk` endpoint in `endpoints.py` has complex logic to handle field-level caching status and add field-specific timestamps to the response.

#### New Implementation
Simplify to clearly indicate when using a cached snapshot:

```python
@router.get("/fire-risk")
async def fire_risk(background_tasks: BackgroundTasks, wait_for_fresh: bool = False):
    """API endpoint to fetch fire risk status"""
    # On first request, ensure we have data
    if not data_cache.current_snapshot:
        logger.info("Initial data fetch (cache empty)")
        await refresh_data_cache(background_tasks)
        
        # If still no data after refresh, error
        if not data_cache.current_snapshot:
            logger.error("No data available after refresh attempt")
            raise HTTPException(
                status_code=503,
                detail="Weather data service unavailable. Please try again later."
            )
    
    # Check if data is stale (older than 60 minutes)
    is_stale = data_cache.is_stale(max_age_minutes=60)
    refresh_in_progress = data_cache.update_in_progress
    
    # If stale and not already refreshing, trigger a refresh
    if is_stale and not refresh_in_progress:
        logger.info("Cache is stale. Triggering refresh.")
        background_tasks.add_task(refresh_data_cache, background_tasks)
    
    # Get the current snapshot
    result = data_cache.current_snapshot["fire_risk_data"].copy()
    
    # Add cache information
    result["cache_info"] = {
        "last_updated": data_cache.last_updated.isoformat() if data_cache.last_updated else None,
        "is_fresh": not is_stale,
        "refresh_in_progress": refresh_in_progress,
        "using_cached_data": data_cache.using_cached_data
    }
    
    # If using cached data, add additional information
    if data_cache.using_cached_data:
        current_time = datetime.now(TIMEZONE)
        cached_time = data_cache.current_snapshot["timestamp"]
        age_str = format_age_string(current_time, cached_time)
        
        result["cached_data"] = {
            "is_cached": True,
            "original_timestamp": cached_time.isoformat(),
            "age": age_str
        }
        
        # Add modal content for UI
        result["modal_content"] = {
            "note": f"Displaying cached weather data from {age_str} ago. Current data is unavailable.",
            "warning_title": "Using Cached Data",
            "warning_issues": ["Unable to fetch fresh data from weather APIs."]
        }
    
    # Add threshold values from config
    from config import THRESH_TEMP, THRESH_HUMID, THRESH_WIND, THRESH_GUSTS, THRESH_SOIL_MOIST
    result["thresholds"] = {
        "temp": THRESH_TEMP,
        "humid": THRESH_HUMID,
        "wind": THRESH_WIND,
        "gusts": THRESH_GUSTS,
        "soil_moist": THRESH_SOIL_MOIST
    }
    
    return result
```

### 5. Update Disk Cache

#### Current Implementation
The disk cache in `cache.py` stores the complex field-level data structure.

#### New Implementation
Simplify to store just the current snapshot:

```python
def _save_cache_to_disk(self) -> bool:
    """Save current cache data to disk"""
    try:
        # Create directory if it doesn't exist
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Prepare data for serialization
        cache_data = {
            "current_snapshot": self._prepare_for_serialization(self.current_snapshot.copy()),
            "last_updated": self.last_updated.isoformat() if self.last_updated else None
        }
        
        # Write to disk
        with open(self.cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)
            
        logger.info(f"Snapshot cache saved to disk: {self.cache_file}")
        return True
    except Exception as e:
        logger.error(f"Error saving cache to disk: {e}")
        return False
```

### 6. UI Changes

The dashboard UI should be updated to:

1. Display a clear banner when showing cached data
2. Show the age of the data prominently
3. Remove field-level "cached data" indicators
4. Provide a "Refresh" button to attempt a manual refresh

## Testing

Create specific tests for the new snapshot-based caching system:

1. Test successful refresh with complete data
2. Test fallback to cache when APIs fail
3. Test regular refresh cycle
4. Test UI indicators for fresh vs. cached data

## Migration Strategy

1. Implement the new system on the `simplified-cache-approach` branch
2. Add comprehensive tests
3. Test with simulated API failures to ensure graceful fallback
4. Perform user acceptance testing to confirm improved clarity
5. Merge to main when satisfied

## Completion Criteria

- Dashboard clearly indicates when data is fresh vs cached
- Users understand exactly how old the data is when viewing cached data
- Regular refresh attempts occur every 10 minutes
- No instances of showing stale data without clearly marking it as such
- Simplified codebase that's easier to maintain

# Fix Plan: Eliminating "<unavailable>" Display in Fire Risk Dashboard

## Bug Analysis

The fire risk dashboard displays "<unavailable>" for weather metrics (temperature, humidity, wind speed, soil moisture) despite having a caching system designed to prevent this situation.

### Root Causes:

1. **Frontend displays "<unavailable>"**: The dashboard.html file between lines 380-478 contains display functions that explicitly render "<unavailable>" when both current and cached data are missing.

2. **Cache initialization gap**: When the application first starts or after a restart, the cache may be empty until the first successful API call.

3. **Backend cache system inconsistencies**: The caching system attempts to use cached values in `cache_refresh.py`, but there's no guarantee that cached values always exist for all metrics.

4. **Missing validation and fallback**: No robust validation to ensure cached data is properly propagated to all responses.

5. **Lack of persistent storage**: The cache is only held in memory and doesn't persist between application restarts.

## Solution Components

### 1. Enhanced Backend Cache System

1. **Implement 4-level fallback hierarchy**:
   - First try: Current API data
   - Second try: Cached data from the current session (in-memory)
   - Third try: Persisted data from previous sessions (loaded from disk)
   - Last resort (only if no persisted data exists): Default values

2. **Add disk persistence**:
   - Save cache data to disk when it's updated
   - Load cache data from disk on startup
   - Use default values only when no disk cache exists

3. **Enhance validation**:
   - Ensure the cache system never returns incomplete data
   - Add fallback mechanisms when no cached data is available

4. **Ensure data propagation**:
   - Verify cached data is correctly merged into the response
   - Fix potential issues in the data merging logic

### 2. Frontend Fixes

1. **Remove "<unavailable>" display code**:
   - Modify all display functions in dashboard.html to never show "<unavailable>"
   - Replace with "Loading..." or a better user experience

2. **Enhance error handling**:
   - Add better error handling for missing data
   - Ensure automatic refresh when data is temporarily unavailable

### 3. Testing Improvements

1. **Add pytest tests**:
   - Create tests to verify the cache system never returns null/None values
   - Test the cache fallback mechanisms with all 4 levels
   - Test disk persistence functionality
   - Test the frontend display functions with various data scenarios

## Implementation Steps

### Part 1: Disk Persistence Implementation

1. **Update `cache.py` with disk persistence**:
   - Add methods to save cache to disk
   - Add methods to load cache from disk
   - Implement timestamp conversion for JSON serialization

2. **Update initialization flow**:
   - Try to load from disk first
   - Fall back to defaults only if disk cache doesn't exist

3. **Update cache update mechanism**:
   - Save to disk after updating in-memory cache

4. **Update fallback logic**:
   - Distinguish between in-memory cache and disk cache
   - Add logging to indicate which level is being used

### Part 2: Completing Original Bug Fix

1. **Update `cache_refresh.py`**:
   - Ensure fallback mechanism properly uses disk cache

2. **Update `endpoints.py`**:
   - Ensure complete validation before returning data to frontend
   - Fix any edge cases in data merging

3. **Update `dashboard.html`**:
   - Remove all "<unavailable>" display code
   - Improve error handling for data display

### Test Implementation

1. **Add disk persistence tests**:
   - Test saving cache to disk
   - Test loading cache from disk
   - Test fallback to disk cache when API fails
   - Test fallback to defaults when no disk cache exists

2. **Complete other tests**:
   - Test cache initialization and fallback flow
   - Test frontend display with various data scenarios
   - Test the complete data flow to ensure "<unavailable>" never appears

## Detailed Code Changes

### 1. Disk Persistence in `cache.py`

```python
# New imports
import json
import os
from pathlib import Path

# In DataCache class
def __init__(self):
    # ... existing code ...
    
    # Cache file path
    self.cache_file = Path("data/cache.json")
    
    # Try to load cached data from disk first
    if self._load_cache_from_disk():
        logger.info("Loaded cached data from disk")
    else:
        # Initialize with default values only if no disk cache exists
        logger.info("No disk cache found, initializing with default values")
        # ... existing initialization code ...

def _load_cache_from_disk(self) -> bool:
    """Load cached data from disk if available."""
    try:
        if not self.cache_file.exists():
            return False
            
        # Load and process disk cache
        # ...
            
        return True
    except Exception as e:
        logger.error(f"Error loading cache from disk: {e}")
        return False
        
def _save_cache_to_disk(self) -> bool:
    """Save current cache data to disk."""
    try:
        # Save current cache to disk
        # ...
            
        return True
    except Exception as e:
        logger.error(f"Error saving cache to disk: {e}")
        return False
```

### 2. Enhanced Validation in `cache.py`

```python
def get_field_value(self, field_name: str) -> Any:
    """Get a value for a field, with multi-level fallbacks."""
    # Try current data
    # Try in-memory cache
    # Try disk cache
    # Fall back to defaults only if necessary
```

### 3. New Tests for Disk Persistence

```python
def test_save_and_load_cache():
    """Test saving cache to disk and loading it back."""
    # Test disk persistence functionality
    
def test_fallback_hierarchy():
    """Test the 4-level fallback hierarchy."""
    # Test each level of fallback
```

## Success Criteria

1. The application never displays "<unavailable>" to the user, regardless of API availability
2. Cache data persists between application restarts
3. The 4-level fallback hierarchy works correctly
4. All tests pass, including the new tests for disk persistence
5. The user experience is improved with better handling of temporarily unavailable data

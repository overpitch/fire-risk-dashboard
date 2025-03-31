# Fire Risk Dashboard System Overview

## Core Components

### Data Sources
- **Synoptic API**: Primary source for temperature, humidity, wind speed, and soil moisture data
- **Weather Underground API**: Source for wind gust data from multiple stations
- **Disk Cache**: Persists data between application restarts to provide fallback when APIs fail

### Core Modules
- **api_clients.py**: Handles communication with external weather APIs
- **cache.py**: Manages in-memory and disk-based data caching
- **cache_refresh.py**: Coordinates data refresh cycles and API calls
- **data_processing.py**: Processes and combines data from multiple sources
- **endpoints.py**: Provides REST API endpoints for the frontend
- **fire_risk_logic.py**: Calculates fire risk levels based on weather data

### Data Flow
1. **Startup**: Application loads cached data from disk if available
2. **Initial Request**: If cache is empty, APIs are queried and data stored in memory and on disk
3. **Regular Refresh**: Background tasks periodically refresh data from APIs
4. **Cache Fallback**: When APIs fail, the system falls back to cached data
5. **Age Display**: When using cached data, age indicators should show when each value was last updated

### Caching Strategy
- **Disk Cache**: Persists across restarts, stored in data/weather_cache.json
- **Field-level Caching**: Each weather parameter (temp, humidity, etc.) has its own timestamp
- **Fallback Logic**: 4-level fallback system:
  1. Direct API data (highest priority)
  2. In-memory cached data
  3. Disk-cached data
  4. Default values (lowest priority)

### UI Components
- Dashboard displays current fire risk with color coding
- Modal appears when using cached data
- Age indicators show next to each value when using cached data
- "Refresh Data" button forces an immediate refresh attempt

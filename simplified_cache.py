import threading
import asyncio
import time
import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import pytz
from pathlib import Path

from config import TIMEZONE, logger

class DataCache:
    # Default values for when no data is available at all
    # These are reasonable fallback values for Sierra City area
    DEFAULT_VALUES = {
        "temperature": 15.0,           # 59°F - mild temperature
        "humidity": 40.0,              # 40% - moderate humidity
        "wind_speed": 5.0,             # 5 mph - light breeze
        "soil_moisture": 20.0,         # 20% - moderately dry soil
        "wind_gust": 8.0               # 8 mph - light gusts
    }
    
    def __init__(self):
        # List of snapshots for historical data (limited to 24 entries)
        self.snapshots: List[Dict[str, Any]] = []
        
        # Current active snapshot (most recent successful fetch)
        self.current_snapshot: Optional[Dict[str, Any]] = None
        
        # Metadata about the current state
        self.last_updated: Optional[datetime] = None
        self.update_in_progress: bool = False
        self.last_update_success: bool = False
        self.using_cached_data: bool = False
        
        # Configuration
        self.max_retries: int = 3
        self.retry_delay: int = 5  # seconds
        self.update_timeout: int = 15  # seconds - max time to wait for a complete refresh
        self.background_refresh_interval: int = 10  # minutes
        self.data_timeout_threshold: int = 30  # minutes - max age before data is considered too old
        self.refresh_task_active: bool = False
        
        # Thread safety
        self._lock = threading.Lock()
        self._update_complete_event = asyncio.Event()
        
        # Set up cache file path - store in data directory
        self.cache_dir = Path("data")
        self.cache_file = self.cache_dir / "weather_cache.json"
        
        # Initialize
        self._load_cache_from_disk()
        
        # If no data was loaded, initialize with a default snapshot
        if not self.current_snapshot:
            current_time = datetime.now(TIMEZONE)
            
            # Create a default snapshot with placeholder data that matches UI expectations
            default_snapshot = {
                "synoptic_data": None,
                "wunderground_data": None,
                "fire_risk_data": {
                    "risk": "Unknown",
                    "explanation": "No data available yet.",
                    "weather": {
                        "air_temp": self.DEFAULT_VALUES["temperature"],
                        "relative_humidity": self.DEFAULT_VALUES["humidity"],
                        "wind_speed": self.DEFAULT_VALUES["wind_speed"],
                        "soil_moisture_15cm": self.DEFAULT_VALUES["soil_moisture"],
                        "wind_gust": self.DEFAULT_VALUES["wind_gust"],
                        # Add data_sources field expected by UI
                        "data_sources": {
                            "weather_station": "SEYC1",
                            "soil_moisture_station": "C3DLA",
                            "wind_gust_stations": ["KCASIERR68", "KCASIERR63", "KCASIERR72"]
                        },
                        # Add data_status field expected by UI
                        "data_status": {
                            "found_stations": [],
                            "missing_stations": [],
                            "issues": []
                        },
                        # Add wind_gust_stations object expected by UI
                        "wind_gust_stations": {
                            "KCASIERR68": {
                                "value": self.DEFAULT_VALUES["wind_gust"],
                                "is_cached": True,
                                "timestamp": current_time
                            }
                        },
                        # Add cached_fields structure expected by UI
                        "cached_fields": {
                            "temperature": True,
                            "humidity": True,
                            "wind_speed": True,
                            "soil_moisture": True,
                            "wind_gust": True,
                            "timestamp": {
                                "temperature": current_time.isoformat(),
                                "humidity": current_time.isoformat(),
                                "wind_speed": current_time.isoformat(),
                                "soil_moisture": current_time.isoformat(),
                                "wind_gust": current_time.isoformat()
                            }
                        },
                        "cache_timestamp": current_time.isoformat()
                    }
                },
                "timestamp": current_time,
                "is_default": True
            }
            
            self.current_snapshot = default_snapshot
            self.snapshots.append(default_snapshot)
            self.last_updated = current_time
            self.using_cached_data = True
            
            logger.info("Initialized with default snapshot")

    def is_stale(self, max_age_minutes: int = 15) -> bool:
        """Check if the current snapshot is stale (older than max_age_minutes)"""
        if self.last_updated is None:
            return True
        
        # Use timezone-aware comparison
        now = datetime.now(TIMEZONE)
        age = now - self.last_updated
        return age > timedelta(minutes=max_age_minutes)
    
    def is_critically_stale(self) -> bool:
        """Check if the data is critically stale (older than data_timeout_threshold)"""
        return self.is_stale(max_age_minutes=self.data_timeout_threshold)
    
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
                "is_default": False
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
            
            # Set the event to signal update completion
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_closed():
                    loop.call_soon_threadsafe(self._update_complete_event.set)
            except Exception as e:
                logger.error(f"Error signaling update completion: {e}")
        
        # Log cache update
        logger.info(f"Complete snapshot cached at {current_time}")
    
    def _load_cache_from_disk(self) -> bool:
        """Load cached data from disk if available.
        
        Returns:
            bool: True if data was loaded successfully, False otherwise
        """
        try:
            if not self.cache_file.exists():
                logger.info(f"Cache file does not exist: {self.cache_file}")
                return False
                
            with open(self.cache_file, 'r') as f:
                disk_cache = json.load(f)
                
            # Validate the loaded data
            if not disk_cache or "current_snapshot" not in disk_cache:
                logger.warning(f"Invalid cache file format: {self.cache_file}")
                return False
            
            # Load the current snapshot
            self.current_snapshot = disk_cache["current_snapshot"]
            
            # Convert ISO timestamp to datetime object
            if "timestamp" in self.current_snapshot:
                self.current_snapshot["timestamp"] = datetime.fromisoformat(self.current_snapshot["timestamp"])
            
            if "last_updated" in disk_cache and disk_cache["last_updated"]:
                self.last_updated = datetime.fromisoformat(disk_cache["last_updated"])
            
            # Load historical snapshots if available
            if "snapshots" in disk_cache:
                self.snapshots = disk_cache["snapshots"]
                # Convert timestamps in all snapshots
                for snapshot in self.snapshots:
                    if "timestamp" in snapshot:
                        snapshot["timestamp"] = datetime.fromisoformat(snapshot["timestamp"])
            else:
                # If no snapshots list, initialize with just the current snapshot
                self.snapshots = [self.current_snapshot]
            
            # Set flag based on age of data
            now = datetime.now(TIMEZONE)
            if self.last_updated:
                age = now - self.last_updated
                if age > timedelta(minutes=60):  # Consider data older than 1 hour as "cached"
                    self.using_cached_data = True
                else:
                    self.using_cached_data = False
            else:
                self.using_cached_data = True
                
            logger.info(f"Successfully loaded cache from disk: {self.cache_file}")
            return True
        except Exception as e:
            logger.error(f"Error loading cache from disk: {e}")
            return False
    
    def _save_cache_to_disk(self) -> bool:
        """Save current cache data to disk.
        
        Returns:
            bool: True if data was saved successfully, False otherwise
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(self.cache_dir, exist_ok=True)
            
            # Prepare data for serialization
            cache_data = {
                "current_snapshot": self._prepare_for_serialization(self.current_snapshot.copy()),
                "snapshots": [self._prepare_for_serialization(snapshot.copy()) for snapshot in self.snapshots],
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
    
    def _prepare_for_serialization(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert datetime objects to ISO strings for JSON serialization recursively."""
        if not data:
            return data
            
        result = {}
        
        for key, value in data.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, dict):
                result[key] = self._prepare_for_serialization(value)
            else:
                result[key] = value
                
        return result
    
    def reset_update_event(self):
        """Reset the update complete event for next update cycle"""
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                loop.call_soon_threadsafe(self._update_complete_event.clear)
            else:
                self._update_complete_event.clear()
        except Exception as e:
            self._update_complete_event.clear()
            logger.error(f"Error resetting update event: {e}")
    
    async def wait_for_update(self, timeout=None):
        """Wait for the current update to complete, with an optional timeout"""
        if timeout is None:
            timeout = self.update_timeout
        try:
            await asyncio.wait_for(self._update_complete_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for data update after {timeout} seconds")
            return False
    
    def get_latest_data(self) -> Dict[str, Any]:
        """Get the latest data from the current snapshot"""
        if not self.current_snapshot:
            logger.warning("No current snapshot available, returning empty dict")
            return {}
            
        return self.current_snapshot

    def get_snapshot_by_time(self, target_time: datetime) -> Optional[Dict[str, Any]]:
        """Get a specific snapshot by timestamp (nearest match)"""
        if not self.snapshots:
            return None
            
        # Find the snapshot closest to the target time
        closest_snapshot = min(self.snapshots, 
            key=lambda s: abs((s.get("timestamp", datetime.now(TIMEZONE)) - target_time).total_seconds())
        )
        
        return closest_snapshot
    
    def mark_as_stale(self):
        """Mark the current data as stale, forcing a refresh on next request"""
        self.using_cached_data = True
        logger.info("Current snapshot marked as stale/cached")

# Initialize the cache
data_cache = DataCache()

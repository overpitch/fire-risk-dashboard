"""Mock utility functions for testing."""

def get_wunderground_data(station_id=None):
    """Mock function for the removed get_wunderground_data API client function."""
    return {
        "observations": [
            {
                "imperial": {
                    "windGust": 3.0
                }
            }
        ]
    }

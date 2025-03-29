import pytest
from data_processing import process_synoptic_data, process_wunderground_data, combine_weather_data, format_age_string
from datetime import datetime, timezone, timedelta

def test_process_synoptic_data_valid_response():
    weather_data = {
        "STATION": [
            {
                "STID": "SEYC1",
                "OBSERVATIONS": {
                    "air_temp_value_1": {"value": 0.5},
                    "relative_humidity_value_1": {"value": 98.0},
                    "wind_speed_value_1": {"value": 0.0}
                }
            },
            {
                "STID": "C3DLA",
                "OBSERVATIONS": {
                    "soil_moisture_value_1": {"value": 22.0}
                }
            }
        ]
    }
    air_temp, relative_humidity, wind_speed, soil_moisture_15cm, found_stations, missing_stations = process_synoptic_data(weather_data)
    assert air_temp == 0.5
    assert relative_humidity == 98.0
    assert wind_speed == 0.0
    assert soil_moisture_15cm == 22.0
    assert found_stations == ["SEYC1", "C3DLA"]
    assert missing_stations == []


def test_process_synoptic_data_missing_stations():
    weather_data = {
        "STATION": [
            {
                "STID": "SEYC1",
                "OBSERVATIONS": {
                    "air_temp_value_1": {"value": 0.5},
                    "relative_humidity_value_1": {"value": 98.0},
                    "wind_speed_value_1": {"value": 0.0}
                }
            }
        ]
    }
    air_temp, relative_humidity, wind_speed, soil_moisture_15cm, found_stations, missing_stations = process_synoptic_data(weather_data)
    assert air_temp == 0.5
    assert relative_humidity == 98.0
    assert wind_speed == 0.0
    assert soil_moisture_15cm is None
    assert found_stations == ["SEYC1"]
    assert missing_stations == ["C3DLA"]


def test_process_synoptic_data_missing_fields():
    weather_data = {
        "STATION": [
            {
                "STID": "SEYC1",
                "OBSERVATIONS": {
                    "relative_humidity_value_1": {"value": 98.0},
                    "wind_speed_value_1": {"value": 0.0}
                }
            },
            {
                "STID": "C3DLA",
                "OBSERVATIONS": {}
            }
        ]
    }
    air_temp, relative_humidity, wind_speed, soil_moisture_15cm, found_stations, missing_stations = process_synoptic_data(weather_data)
    assert air_temp is None
    assert relative_humidity == 98.0
    assert wind_speed == 0.0
    assert soil_moisture_15cm is None
    assert found_stations == ["SEYC1", "C3DLA"]
    assert missing_stations == []


def test_process_synoptic_data_empty_response():
    weather_data = None
    air_temp, relative_humidity, wind_speed, soil_moisture_15cm, found_stations, missing_stations = process_synoptic_data(weather_data)
    assert air_temp is None
    assert relative_humidity is None
    assert wind_speed is None
    assert soil_moisture_15cm is None
    assert found_stations == []
    assert missing_stations == ["C3DLA", "SEYC1"]

def test_process_synoptic_data_malformed_response():
    weather_data = {"BAD_KEY": []}
    air_temp, relative_humidity, wind_speed, soil_moisture_15cm, found_stations, missing_stations = process_synoptic_data(weather_data)
    assert air_temp is None
    assert relative_humidity is None
    assert wind_speed is None
    assert soil_moisture_15cm is None
    assert found_stations == []
    assert missing_stations == ["C3DLA", "SEYC1"]

def test_process_synoptic_data_various_soil_moisture():
    weather_data = {
        "STATION": [
            {
                "STID": "SEYC1",
                "OBSERVATIONS": {
                    "air_temp_value_1": {"value": 0.5},
                    "relative_humidity_value_1": {"value": 98.0},
                    "wind_speed_value_1": {"value": 0.0}
                }
            },
            {
                "STID": "C3DLA",
                "OBSERVATIONS": {
                    "soil_moisture_0.15m_value_1": {"value": 15.0},
                    "soil_moisture_15cm_value_2": {"value": 16.0},
                    "soil_moisture_15_cm_value_3": {"value": 17.0},
                    "soil_moisture_value_1": {"value": 22.0}
                }
            }
        ]
    }
    air_temp, relative_humidity, wind_speed, soil_moisture_15cm, found_stations, missing_stations = process_synoptic_data(weather_data)
    assert air_temp == 0.5
    assert relative_humidity == 98.0
    assert wind_speed == 0.0
    assert soil_moisture_15cm == 15.0
    assert found_stations == ["SEYC1", "C3DLA"]
    assert missing_stations == []


def test_process_wunderground_data_valid():
    wunderground_data = {
        "KCASIERR68": {"observations": [{"imperial": {"windGust": 3.0}}]},
        "KCACEDAR2": {"observations": [{"imperial": {"windGust": 5.0}}]}
    }

    avg_wind_gust, station_data, found_stations, missing_stations = process_wunderground_data(wunderground_data)

    assert avg_wind_gust == 4.0
    assert station_data["KCASIERR68"]["value"] == 3.0
    assert station_data["KCACEDAR2"]["value"] == 5.0
    assert found_stations == ["KCASIERR68", "KCACEDAR2"]
    assert missing_stations == []


def test_process_wunderground_data_missing_stations():
    wunderground_data = {
        "KCASIERR68": {"observations": [{"imperial": {"windGust": 3.0}}]}
    }
    avg_wind_gust, station_data, found_stations, missing_stations = process_wunderground_data(wunderground_data)
    assert avg_wind_gust == 3.0
    assert station_data["KCASIERR68"]["value"] == 3.0
    assert station_data["KCACEDAR2"]["value"] is None  # Missing station
    assert found_stations == ["KCASIERR68"]
    assert missing_stations == ["KCACEDAR2"]


def test_process_wunderground_data_missing_fields():
    wunderground_data = {
        "KCASIERR68": {"observations": [{"imperial": {}}]},  # Missing windGust
        "KCACEDAR2": {"observations": [{"imperial": {"windGust": 5.0}}]}
    }
    avg_wind_gust, station_data, found_stations, missing_stations = process_wunderground_data(wunderground_data)
    assert avg_wind_gust == 5.0
    assert station_data["KCASIERR68"]["value"] is None
    assert station_data["KCACEDAR2"]["value"] == 5.0
    assert found_stations == ["KCACEDAR2"]
    assert missing_stations == ["KCASIERR68"]


def test_process_wunderground_data_cached_data():
    wunderground_data = {
        "KCASIERR68": {"observations": [{"imperial": {"windGust": 3.0}}]},
        "KCACEDAR2": None  # Simulate missing data for this station
    }
    current_time = datetime.now(timezone.utc)
    cached_time = current_time - timedelta(minutes=30)  # Cached data is 30 minutes old
    cached_data = {
        "fields": {
            "wind_gust": {
                "stations": {
                    "KCACEDAR2": {"value": 6.0, "timestamp": cached_time}
                }
            }
        }
    }

    avg_wind_gust, station_data, found_stations, missing_stations = process_wunderground_data(wunderground_data, cached_data)

    assert avg_wind_gust == 4.5
    assert station_data["KCASIERR68"]["value"] == 3.0
    assert station_data["KCACEDAR2"]["value"] == 6.0
    assert station_data["KCACEDAR2"]["is_cached"] == True
    assert found_stations == ["KCASIERR68"]  # KCACEDAR2 is not in found_stations because it uses cached data
    assert missing_stations == []


def test_process_wunderground_data_expired_cached_data():
    wunderground_data = {
        "KCASIERR68": {"observations": [{"imperial": {"windGust": 3.0}}]},
        "KCACEDAR2": None  # Simulate missing data for this station
    }
    current_time = datetime.now(timezone.utc)
    cached_time = current_time - timedelta(hours=2)  # Cached data is 2 hours old (expired)
    cached_data = {
        "fields": {
            "wind_gust": {
                "stations": {
                    "KCACEDAR2": {"value": 6.0, "timestamp": cached_time}
                }
            }
        }
    }

    avg_wind_gust, station_data, found_stations, missing_stations = process_wunderground_data(wunderground_data, cached_data)

    assert avg_wind_gust == 3.0
    assert station_data["KCASIERR68"]["value"] == 3.0
    assert station_data["KCACEDAR2"]["value"] is None
    assert found_stations == ["KCASIERR68"]
    assert missing_stations == ["KCACEDAR2"]


def test_process_wunderground_data_error_handling():
    wunderground_data = {
        "KCASIERR68": {"observations": [{"imperial": {"windGust": 3.0}}]},
        "KCACEDAR2": {"observations": []}  # Empty observations list, should be handled
    }
    avg_wind_gust, station_data, found_stations, missing_stations = process_wunderground_data(wunderground_data)
    assert avg_wind_gust == 3.0
    assert station_data["KCASIERR68"]["value"] == 3.0
    assert station_data["KCACEDAR2"]["value"] is None
    assert found_stations == ["KCASIERR68"]
    assert missing_stations == ["KCACEDAR2"]


def test_combine_weather_data_valid():
    synoptic_data = {
        "STATION": [
            {
                "STID": "SEYC1",
                "OBSERVATIONS": {
                    "air_temp_value_1": {"value": 0.5},
                    "relative_humidity_value_1": {"value": 98.0},
                    "wind_speed_value_1": {"value": 0.0}
                }
            },
            {
                "STID": "C3DLA",
                "OBSERVATIONS": {
                    "soil_moisture_value_1": {"value": 22.0}
                }
            }
        ]
    }
    wunderground_data = {
        "KCASIERR68": {"observations": [{"imperial": {"windGust": 3.0}}]},
        "KCACEDAR2": {"observations": [{"imperial": {"windGust": 5.0}}]}
    }

    combined_data = combine_weather_data(synoptic_data, wunderground_data)

    assert combined_data["air_temp"] == 0.5
    assert combined_data["relative_humidity"] == 98.0
    assert combined_data["wind_speed"] == 0.0
    assert combined_data["soil_moisture_15cm"] == 22.0
    assert combined_data["wind_gust"] == 4.0
    assert combined_data["data_sources"]["weather_station"] == "SEYC1"
    assert combined_data["data_sources"]["soil_moisture_station"] == "C3DLA"
    assert combined_data["data_sources"]["wind_gust_stations"] == ["KCASIERR68", "KCACEDAR2"]
    assert combined_data["data_status"]["found_stations"] == ["SEYC1", "C3DLA", "KCASIERR68", "KCACEDAR2"]
    assert combined_data["data_status"]["missing_stations"] == []
    assert combined_data["data_status"]["issues"] == []
    assert combined_data["cached_fields"] == {
        "temperature": False,
        "humidity": False,
        "wind_speed": False,
        "soil_moisture": False,
        "wind_gust": False
    }


def test_combine_weather_data_missing_data():
    synoptic_data = {
        "STATION": [
            {
                "STID": "SEYC1",
                "OBSERVATIONS": {
                    "air_temp_value_1": {"value": 0.5},
                    "wind_speed_value_1": {"value": 0.0}
                }
            }
        ]
    }

    wunderground_data = {
        "KCASIERR68": {"observations": []}
    }

    combined_data = combine_weather_data(synoptic_data, wunderground_data)
    assert combined_data["relative_humidity"] is None
    assert combined_data["soil_moisture_15cm"] is None
    assert combined_data["wind_gust"] is None
    assert combined_data["data_status"]["missing_stations"] == ["C3DLA", "KCACEDAR2"]
    assert "Humidity data missing from station SEYC1" in combined_data["data_status"]["issues"]
    assert "Soil moisture data missing from station C3DLA" in combined_data["data_status"]["issues"]
    assert "Wind gust data missing from all Weather Underground stations" in combined_data["data_status"]["issues"]


def test_combine_weather_data_cached_data():
    synoptic_data = {
        "STATION": [
            {
                "STID": "SEYC1",
                "OBSERVATIONS": {
                    "air_temp_value_1": {"value": 0.5},
                    "relative_humidity_value_1": {"value": 98.0},
                    "wind_speed_value_1": {"value": 0.0}
                }
            },
            {
                "STID": "C3DLA",
                "OBSERVATIONS": {
                    "soil_moisture_value_1": {"value": 22.0}
                }
            }
        ]
    }
    wunderground_data = {
        "KCASIERR68": None,
        "KCACEDAR2": {"observations": [{"imperial": {"windGust": 5.0}}]}
    }
    current_time = datetime.now(timezone.utc)
    cached_time = current_time - timedelta(minutes=30)
    cached_data = {
        "fields": {
            "wind_gust": {
                "stations": {
                    "KCASIERR68": {"value": 7.0, "timestamp": cached_time}
                }
            }
        }
    }
    combined_data = combine_weather_data(synoptic_data, wunderground_data, cached_data)
    assert combined_data["wind_gust"] == 6.0
    assert combined_data["wind_gust_stations"]["KCASIERR68"]["is_cached"] == True
    assert combined_data["cached_fields"]["wind_gust"] == True


def test_format_age_string():
    current_time = datetime.now(timezone.utc)
    cached_time = current_time - timedelta(minutes=5)
    assert format_age_string(current_time, cached_time) == "5 minutes"

    cached_time = current_time - timedelta(hours=2)
    assert format_age_string(current_time, cached_time) == "2 hours"

    cached_time = current_time - timedelta(days=1)
    assert format_age_string(current_time, cached_time) == "1 day"

    cached_time = current_time - timedelta(days=3)
    assert format_age_string(current_time, cached_time) == "3 days"

    cached_time = current_time
    assert format_age_string(current_time, cached_time) == "0 minutes"

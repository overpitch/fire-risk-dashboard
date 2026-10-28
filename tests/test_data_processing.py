import pytest
from data_processing import process_synoptic_data, combine_weather_data, format_age_string

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
            },
            {
                "STID": "629PG",
                "OBSERVATIONS": {
                    "wind_speed_value_1": {"value": 0.0},
                    "wind_gust_value_1": {"value": 3.0}
                }
            }
        ]
    }
    air_temp, relative_humidity, wind_speed, wind_gust, soil_moisture_15cm, found_stations, missing_stations = process_synoptic_data(weather_data)
    assert air_temp == 0.5
    assert relative_humidity == 98.0
    assert wind_speed == 0.0
    assert wind_gust == 3.0
    assert soil_moisture_15cm == 22.0
    assert found_stations == ["SEYC1", "C3DLA", "629PG"]
    assert missing_stations == []


def test_process_synoptic_data_missing_stations():
    weather_data = {
        "STATION": [
            {
                "STID": "SEYC1",
                "OBSERVATIONS": {
                    "air_temp_value_1": {"value": 0.5},
                    "relative_humidity_value_1": {"value": 98.0},
                    "wind_speed_value_1": {"value": 0.0}  # Ignored: wind comes from 629PG
                }
            }
        ]
    }
    air_temp, relative_humidity, wind_speed, wind_gust, soil_moisture_15cm, found_stations, missing_stations = process_synoptic_data(weather_data)
    assert air_temp == 0.5
    assert relative_humidity == 98.0
    assert wind_speed is None
    assert wind_gust is None
    assert soil_moisture_15cm is None
    assert found_stations == ["SEYC1"]
    assert missing_stations == ["C3DLA", "629PG"]


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
            },
            {
                "STID": "629PG",
                "OBSERVATIONS": {
                    "wind_speed_value_1": {"value": 0.0}
                }
            }
        ]
    }
    air_temp, relative_humidity, wind_speed, wind_gust, soil_moisture_15cm, found_stations, missing_stations = process_synoptic_data(weather_data)
    assert air_temp is None
    assert relative_humidity == 98.0
    assert wind_speed == 0.0
    assert wind_gust is None
    assert soil_moisture_15cm is None
    assert found_stations == ["SEYC1", "C3DLA", "629PG"]
    assert missing_stations == []


def test_process_synoptic_data_empty_response():
    weather_data = None
    air_temp, relative_humidity, wind_speed, wind_gust, soil_moisture_15cm, found_stations, missing_stations = process_synoptic_data(weather_data)
    assert air_temp is None
    assert relative_humidity is None
    assert wind_speed is None
    assert wind_gust is None
    assert soil_moisture_15cm is None
    assert found_stations == []
    assert missing_stations == ["C3DLA", "SEYC1", "629PG"]

def test_process_synoptic_data_malformed_response():
    weather_data = {"BAD_KEY": []}
    air_temp, relative_humidity, wind_speed, wind_gust, soil_moisture_15cm, found_stations, missing_stations = process_synoptic_data(weather_data)
    assert air_temp is None
    assert relative_humidity is None
    assert wind_speed is None
    assert wind_gust is None
    assert soil_moisture_15cm is None
    assert found_stations == []
    assert missing_stations == ["C3DLA", "SEYC1", "629PG"]

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
            },
            {
                "STID": "629PG",
                "OBSERVATIONS": {
                    "wind_speed_value_1": {"value": 0.0},
                    "wind_gust_value_1": {"value": 3.0}
                }
            }
        ]
    }
    air_temp, relative_humidity, wind_speed, wind_gust, soil_moisture_15cm, found_stations, missing_stations = process_synoptic_data(weather_data)
    assert air_temp == 0.5
    assert relative_humidity == 98.0
    assert wind_speed == 0.0
    assert wind_gust == 3.0
    assert soil_moisture_15cm == 15.0
    assert found_stations == ["SEYC1", "C3DLA", "629PG"]
    assert missing_stations == []


def full_synoptic_response(wind_gust=3.0):
    """A response from all three stations: temperature/humidity, soil moisture and wind."""
    wind_observations = {"wind_speed_value_1": {"value": 0.0}}
    if wind_gust is not None:
        wind_observations["wind_gust_value_1"] = {"value": wind_gust}
    return {
        "STATION": [
            {
                "STID": "SEYC1",
                "OBSERVATIONS": {
                    "air_temp_value_1": {"value": 0.5},
                    "relative_humidity_value_1": {"value": 98.0}
                }
            },
            {
                "STID": "C3DLA",
                "OBSERVATIONS": {
                    "soil_moisture_value_1": {"value": 22.0}
                }
            },
            {
                "STID": "629PG",
                "OBSERVATIONS": wind_observations
            }
        ]
    }


def test_combine_weather_data_valid():
    combined_data = combine_weather_data(full_synoptic_response())

    assert combined_data["air_temp"] == 0.5
    assert combined_data["relative_humidity"] == 98.0
    assert combined_data["wind_speed"] == 0.0
    assert combined_data["soil_moisture_15cm"] == 22.0
    assert combined_data["wind_gust"] == 3.0
    assert combined_data["data_sources"] == {
        "weather_station": "SEYC1",
        "soil_moisture_station": "C3DLA",
        "wind_gust_station": "629PG"
    }
    assert combined_data["wind_gust_stations"]["629PG"]["value"] == 3.0
    assert combined_data["wind_gust_stations"]["629PG"]["is_cached"] is False
    assert combined_data["data_status"]["found_stations"] == ["SEYC1", "C3DLA", "629PG"]
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
                    "air_temp_value_1": {"value": 0.5}
                }
            }
        ]
    }

    combined_data = combine_weather_data(synoptic_data)
    assert combined_data["air_temp"] == 0.5
    assert combined_data["relative_humidity"] is None
    assert combined_data["wind_speed"] is None
    assert combined_data["soil_moisture_15cm"] is None
    assert combined_data["wind_gust"] is None
    assert combined_data["data_status"]["missing_stations"] == ["C3DLA", "629PG"]
    assert combined_data["data_status"]["issues"] == [
        "Humidity data missing from station SEYC1",
        "Wind speed data missing from station 629PG",
        "Soil moisture data missing from station C3DLA",
        "Wind gust data missing from station 629PG",
    ]


def cached_wind_gust(value, age):
    """Saved weather fields with a wind gust reading taken `age` ago."""
    return {"fields": {"wind_gust": {"value": value, "timestamp": datetime.now(timezone.utc) - age}}}


def test_combine_weather_data_cached_data():
    """With no live gust reading, a cached one under an hour old is used and flagged as cached."""
    combined_data = combine_weather_data(full_synoptic_response(wind_gust=None),
                                         cached_wind_gust(7.0, timedelta(minutes=30)))

    assert combined_data["wind_gust"] == 7.0
    assert combined_data["wind_gust_stations"]["629PG"]["is_cached"] is True
    assert combined_data["cached_fields"]["wind_gust"] is True
    assert combined_data["data_status"]["issues"] == []


def test_combine_weather_data_live_gust_preferred_over_cache():
    combined_data = combine_weather_data(full_synoptic_response(wind_gust=3.0),
                                         cached_wind_gust(7.0, timedelta(minutes=30)))

    assert combined_data["wind_gust"] == 3.0
    assert combined_data["cached_fields"]["wind_gust"] is False


def test_combine_weather_data_expired_cached_data():
    """A cached gust reading over an hour old is not used."""
    combined_data = combine_weather_data(full_synoptic_response(wind_gust=None),
                                         cached_wind_gust(7.0, timedelta(hours=2)))

    assert combined_data["wind_gust"] is None
    assert combined_data["cached_fields"]["wind_gust"] is False
    assert "Wind gust data missing from station 629PG" in combined_data["data_status"]["issues"]

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

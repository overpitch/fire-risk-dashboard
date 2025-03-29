import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from cache import DataCache

@pytest.fixture
def cache():
    return DataCache()


def test_is_stale_no_data(cache):
    assert cache.is_stale() is True


def test_is_stale_fresh_data(cache):
    cache.last_updated = datetime.now(timezone.utc)
    assert cache.is_stale() is False


def test_is_stale_old_data(cache):
    cache.last_updated = datetime.now(timezone.utc) - timedelta(minutes=20)
    assert cache.is_stale() is True


def test_is_critically_stale_no_data(cache):
    assert cache.is_critically_stale() is True


def test_is_critically_stale_fresh_data(cache):
    cache.last_updated = datetime.now(timezone.utc)
    assert cache.is_critically_stale() is False


def test_is_critically_stale_old_data(cache):
    cache.last_updated = datetime.now(timezone.utc) - timedelta(minutes=40)  # Older than the 30-minute threshold
    assert cache.is_critically_stale() is True


def test_update_cache(cache):
    synoptic_data = {"test": "synoptic"}
    wunderground_data = {"test": "wunderground"}
    fire_risk_data = {"risk": "low"}

    cache.update_cache(synoptic_data, wunderground_data, fire_risk_data)

    assert cache.synoptic_data == synoptic_data
    assert cache.wunderground_data == wunderground_data
    assert cache.fire_risk_data == fire_risk_data
    assert cache.last_updated is not None
    assert cache.last_update_success is True
    assert cache.last_valid_data["synoptic_data"] == synoptic_data
    assert cache.last_valid_data["wunderground_data"] == wunderground_data
    assert cache.last_valid_data["fire_risk_data"] == fire_risk_data
    assert cache.last_valid_data["timestamp"] is not None


@pytest.mark.asyncio
async def test_wait_for_update(cache):
    # Simulate an update in a separate thread
    async def update_cache_async():
        await asyncio.sleep(0.1)  # Simulate some delay
        cache.update_cache({}, {}, {})

    asyncio.create_task(update_cache_async())
    assert await cache.wait_for_update() is True


@pytest.mark.asyncio
async def test_wait_for_update_timeout(cache):
    cache.update_timeout = 0.01  # Set a very short timeout
    assert await cache.wait_for_update() is False


def test_reset_update_event(cache):
    # Set the event manually
    cache._update_complete_event.set()
    assert cache._update_complete_event.is_set() is True

    cache.reset_update_event()
    assert cache._update_complete_event.is_set() is False

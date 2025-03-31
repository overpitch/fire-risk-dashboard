import pytest
from unittest.mock import patch, AsyncMock
from cache import data_cache

@pytest.mark.asyncio
@patch('endpoints.refresh_data_cache', new_callable=AsyncMock)
async def test_toggle_test_mode_resets_cached_fields(mock_refresh_data_cache, client):
    """Test that toggling test mode OFF properly resets all cached field flags."""
    mock_refresh_data_cache.return_value = True
    
    # Store original cached_fields state to restore later
    original_cached_fields = data_cache.cached_fields.copy()
    original_using_cached_data = data_cache.using_cached_data
    
    try:
        # Setup: First set all cached fields to True (as if test mode was ON)
        data_cache.using_cached_data = True
        for field in data_cache.cached_fields:
            data_cache.cached_fields[field] = True
            
        # Verify our setup worked
        assert data_cache.using_cached_data is True
        assert all(data_cache.cached_fields.values()), "Not all cached fields were set to True in test setup"
            
        # Now disable test mode
        response = await client.get("/toggle-test-mode?enable=false")
            
        # Verify response
        assert response.status_code == 200
        assert response.json()["mode"] == "normal"
            
        # Verify using_cached_data is set to False
        assert data_cache.using_cached_data is False
            
        # Verify ALL cached fields were reset to False
        for field, value in data_cache.cached_fields.items():
            assert value is False, f"Field {field} was not reset to False after disabling test mode"
            
        # Verify refresh was called
        mock_refresh_data_cache.assert_awaited_once()
    
    finally:
        # Restore original state
        data_cache.using_cached_data = original_using_cached_data
        data_cache.cached_fields = original_cached_fields

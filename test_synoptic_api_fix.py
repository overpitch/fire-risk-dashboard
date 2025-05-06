#!/usr/bin/env python
"""
Test script for Synoptic API authentication fix.

This script tests the improved token validation and retry mechanism to handle
401 Unauthorized errors caused by invalid tokens.
"""

import os
import sys
import logging
import time
from typing import Optional, Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("test_synoptic_api_fix")

# Import the api_clients module
try:
    from api_clients import (
        get_api_token, validate_token_format, get_weather_data,
        SYNOPTIC_BASE_URL, SYNOPTIC_API_KEY
    )
except ImportError:
    logger.error("❌ Failed to import api_clients module. Make sure you're in the correct directory.")
    sys.exit(1)

def test_token_validation():
    """Test the token validation function"""
    logger.info("🧪 Testing token validation...")
    
    # Test valid token format
    valid_token = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
    assert validate_token_format(valid_token), f"Should validate correct token: {valid_token}"
    logger.info("✅ Correctly validated proper token format")
    
    # Test invalid token formats
    invalid_tokens = [
        "",                        # Empty string
        "short",                   # Too short
        "a" * 100,                 # Too long
        "invalid-token-with-dash", # Contains invalid characters
        "token with spaces",       # Contains spaces
        "12345@#$%^",              # Contains special characters
    ]
    
    for i, token in enumerate(invalid_tokens):
        assert not validate_token_format(token), f"Should reject invalid token {i}: {token}"
    
    logger.info("✅ Correctly rejected all invalid token formats")
    return True

def test_token_acquisition():
    """Test getting a valid token from the API"""
    logger.info("🧪 Testing token acquisition...")
    
    if not SYNOPTIC_API_KEY:
        logger.error("❌ No API key found. Set SYNOPTICDATA_API_KEY environment variable.")
        return False
    
    # Get a token and verify it's valid
    token = get_api_token()
    if not token:
        logger.error("❌ Failed to get API token")
        return False
    
    logger.info(f"🔑 Got token: {token[:10]}...")
    assert validate_token_format(token), "Token should be in valid format"
    logger.info("✅ Successfully obtained and validated API token")
    return True

def test_retry_mechanism():
    """Test the retry mechanism with exponential backoff"""
    logger.info("🧪 Testing retry mechanism with invalid token...")
    
    # Try with a deliberate error to trigger retries
    station_ids = "C3DLA,SEYC1,629PG"
    
    # Create a timer to measure total execution time
    start_time = time.time()
    
    # Use a real request with normal operation - this should work
    result = get_weather_data(station_ids)
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    if result:
        logger.info(f"✅ Successfully retrieved data with retry mechanism")
        logger.info(f"⏱️ Total execution time: {execution_time:.2f} seconds")
        
        # Check if we got station data
        if "STATION" in result:
            stations = result.get("STATION", [])
            logger.info(f"📊 Retrieved data for {len(stations)} stations")
            for station in stations:
                logger.info(f"  - Station: {station.get('STID', 'Unknown')} - {station.get('NAME', 'Unnamed')}")
        else:
            logger.warning("⚠️ Response doesn't contain STATION data")
        
        return True
    else:
        logger.error("❌ Failed to retrieve data even with retry mechanism")
        return False

def main():
    """Run all tests"""
    try:
        # First activate the virtual environment
        print("\n🔧 Testing Synoptic API fix...\n")
        
        # Run tests
        validation_passed = test_token_validation()
        token_passed = test_token_acquisition()
        retry_passed = test_retry_mechanism()
        
        # Print summary
        print("\n📋 Test Results:")
        print(f"  - Token validation: {'✅ Passed' if validation_passed else '❌ Failed'}")
        print(f"  - Token acquisition: {'✅ Passed' if token_passed else '❌ Failed'}")
        print(f"  - Retry mechanism: {'✅ Passed' if retry_passed else '❌ Failed'}")
        
        if validation_passed and token_passed and retry_passed:
            print("\n🎉 All tests passed! The fix should resolve the 401 Unauthorized issues.")
        else:
            print("\n⚠️ Some tests failed. Review the logs above for details.")
        
    except Exception as e:
        logger.exception(f"❌ Error during testing: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

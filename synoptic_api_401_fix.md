# Synoptic API 401 Unauthorized Issue Fix

## Problem Summary

The fire-risk-dashboard application was experiencing intermittent 401 Unauthorized errors when making requests to the Synoptic API. The specific error message was:

```
"Invalid token. Be sure to use a token generated from your API Key, and not the key itself."
```

Despite the application correctly obtaining tokens before making data requests, these errors occurred frequently, requiring multiple retries to eventually succeed.

## Root Cause Analysis

After analyzing the logs and code, we identified several contributing factors:

1. Token validation issues: The system was not validating token formats before using them
2. Immediate retries: The system was retrying failed requests immediately without giving the API time to stabilize
3. Limited retry attempts: With only 2 retry attempts, the system often exhausted all retries before succeeding

Based on the error message and the intermittent nature of the failures, this appears to be an issue on the Synoptic API's end with token validation, where some generated tokens may not be immediately recognized by their system.

## Solution Implemented

Our fix addresses these issues with a multi-faceted approach:

1. **Token format validation**:
   - Added a `validate_token_format()` function that checks tokens follow the expected format
   - Rejects malformed tokens immediately, preventing failed API calls
   - Utilizes regex pattern matching to ensure tokens are alphanumeric strings of the correct length

2. **Exponential backoff with jitter**:
   - Implemented a `calculate_backoff_time()` function to determine wait times between retries
   - Initial 1-second delay doubles with each retry (1s, 2s, 4s, 8s, etc.)
   - Added small random jitter (±10%) to prevent thundering herd issues
   - Max delay capped at 30 seconds

3. **Increased retry limit**:
   - Extended maximum retries from 2 to 4
   - With the exponential backoff, this provides more time for the API to stabilize

4. **Improved error handling**:
   - Added specific error detection for "Invalid token" error messages
   - Better logging of token validation steps for easier debugging

## Testing

All improvements have been verified with a comprehensive test script (`test_synoptic_api_fix.py`) that checks:

1. Token validation logic
2. Token acquisition from the API
3. The retry mechanism with real API requests

The tests confirmed that our solution successfully addresses the 401 Unauthorized issues.

## Monitoring Recommendations

To ensure the solution continues to work:

1. Monitor error rates for 401 Unauthorized responses
2. Track the success rate of requests after applying the fix
3. Consider implementing a dead-letter queue for any requests that still fail after retries
4. If issues persist, contact Synoptic API support with detailed logs

## Future Improvements

Potential enhancements to consider:

1. Implement a token caching mechanism to reuse valid tokens
2. Add a circuit breaker to temporarily stop requests during prolonged API outages
3. Create a proactive monitoring system that alerts on repeated authentication failures
4. Consider implementing a proxy service that maintains a pool of pre-validated tokens

## References

- Original issue logs: May 5, 2025 production logs
- Modified files: `api_clients.py`
- Test script: `test_synoptic_api_fix.py`

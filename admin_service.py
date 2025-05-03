import hashlib
import time
import os
from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta
from config import logger

# Admin PIN (hardcoded for now, can be moved to environment variables later)
ADMIN_PIN = "1446"

# Store for failed login attempts, structured as:
# { "ip_address": { "attempts": [timestamp1, timestamp2, ...], "locked_until": timestamp } }
# This is stored in memory and will reset when the server restarts
failed_attempts: Dict[str, Dict[str, any]] = {}

# Security settings
MAX_ATTEMPTS = 5             # Maximum number of failed attempts before lockout
LOCKOUT_DURATION = 30 * 60   # Lockout duration in seconds (30 minutes)
ATTEMPT_WINDOW = 60 * 60     # Time window for counting attempts (1 hour)

def hash_pin(pin: str) -> str:
    """
    Hash the PIN using a secure hash function
    Using a simple hash without salt for MVP - can be enhanced in future
    """
    return hashlib.sha256(pin.encode()).hexdigest()

def verify_pin(provided_pin: str, ip_address: str) -> Tuple[bool, str]:
    """
    Verify the provided PIN against the stored PIN
    Implements rate limiting to prevent brute force attacks
    
    Returns:
        Tuple[bool, str]: (is_valid, error_message)
    """
    # Check if IP is locked out
    if ip_address in failed_attempts and "locked_until" in failed_attempts[ip_address]:
        lockout_time = failed_attempts[ip_address]["locked_until"]
        if lockout_time > time.time():
            # Calculate remaining lockout time in minutes
            remaining_mins = int((lockout_time - time.time()) / 60) + 1
            return False, f"Too many failed attempts. Try again in {remaining_mins} minutes."
        else:
            # Lockout period is over, reset the record
            del failed_attempts[ip_address]["locked_until"]
    
    # Initialize attempt tracking for this IP if not exists
    if ip_address not in failed_attempts:
        failed_attempts[ip_address] = {"attempts": []}
    
    # Clean up old attempts outside the window
    current_time = time.time()
    failed_attempts[ip_address]["attempts"] = [
        t for t in failed_attempts[ip_address]["attempts"] 
        if t > current_time - ATTEMPT_WINDOW
    ]
    
    # Verify the PIN
    if hash_pin(provided_pin) == hash_pin(ADMIN_PIN):  # Using the same hash function for both
        # Successful login, reset attempts
        failed_attempts[ip_address]["attempts"] = []
        return True, ""
    else:
        # Failed login, record the attempt
        failed_attempts[ip_address]["attempts"].append(current_time)
        
        # Check if max attempts exceeded
        if len(failed_attempts[ip_address]["attempts"]) >= MAX_ATTEMPTS:
            # Lock out the IP
            failed_attempts[ip_address]["locked_until"] = current_time + LOCKOUT_DURATION
            return False, f"Too many failed attempts. Account locked for {LOCKOUT_DURATION // 60} minutes."
        else:
            # Not locked out yet, but PIN is incorrect
            remaining = MAX_ATTEMPTS - len(failed_attempts[ip_address]["attempts"])
            return False, f"Invalid PIN. {remaining} attempts remaining."

def reset_attempts(ip_address: str) -> None:
    """Reset failed attempts for an IP address"""
    if ip_address in failed_attempts:
        del failed_attempts[ip_address]

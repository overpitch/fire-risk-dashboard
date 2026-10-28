import secrets
import time
import os
from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta
from config import logger

# Admin password comes from the environment (set ADMIN_PASSWORD in Render).
# If it is not set, admin login is disabled rather than falling back to a default.
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    logger.warning("ADMIN_PASSWORD is not set - admin login is disabled.")

# Store for failed login attempts, structured as:
# { "ip_address": { "attempts": [timestamp1, timestamp2, ...], "locked_until": timestamp } }
# This is stored in memory and will reset when the server restarts
failed_attempts: Dict[str, Dict[str, any]] = {}

# Security settings
MAX_ATTEMPTS = 5             # Maximum number of failed attempts before lockout
LOCKOUT_DURATION = 30 * 60   # Lockout duration in seconds (30 minutes)
ATTEMPT_WINDOW = 60 * 60     # Time window for counting attempts (1 hour)

def _prune_failed_attempts() -> None:
    """Drop records with no recent attempts and no active lockout, so the store stays small."""
    now = time.time()
    for ip in [ip for ip, record in failed_attempts.items()
               if record.get("locked_until", 0) <= now
               and not any(t > now - ATTEMPT_WINDOW for t in record["attempts"])]:
        del failed_attempts[ip]

def verify_password(provided_password: str, ip_address: str) -> Tuple[bool, str]:
    """
    Verify the provided password against ADMIN_PASSWORD
    Implements rate limiting to prevent brute force attacks
    
    Returns:
        Tuple[bool, str]: (is_valid, error_message)
    """
    if not ADMIN_PASSWORD:
        return False, "Admin login is not configured."

    _prune_failed_attempts()

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
    
    # Verify the password (constant-time comparison)
    if secrets.compare_digest(provided_password.encode(), ADMIN_PASSWORD.encode()):
        # Successful login, forget this visitor's failed attempts
        del failed_attempts[ip_address]
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
            # Not locked out yet, but password is incorrect
            remaining = MAX_ATTEMPTS - len(failed_attempts[ip_address]["attempts"])
            return False, f"Invalid password. {remaining} attempts remaining."


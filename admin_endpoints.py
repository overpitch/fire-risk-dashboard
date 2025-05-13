from fastapi import APIRouter, Request, Form, Cookie, Response, BackgroundTasks, HTTPException, UploadFile, File, Body, status, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import shutil
import os
from fastapi.templating import Jinja2Templates
import pathlib
import os
import time
from typing import Optional, List, Dict, Any
import secrets
import json
from pydantic import BaseModel, EmailStr

from config import logger
from cache import data_cache
from cache_refresh import refresh_data_cache
from admin_service import verify_pin, reset_attempts
from subscriber_service import get_active_subscribers, bulk_import_subscribers
from file_processor import process_subscriber_file
from email_service import send_test_orange_to_red_alert, send_custom_email_to_subscribers # Added new import

# Create a router for admin endpoints
router = APIRouter()

# Pydantic model for sending custom email
class CustomEmailPayload(BaseModel):
    subject: str
    html_content: str
    recipients: List[EmailStr]

# Pydantic model for test conditions payload
class TestConditionsPayload(BaseModel):
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    average_winds: Optional[float] = None # Matches JS key
    wind_gust: Optional[float] = None
    soil_moisture: Optional[float] = None # Matches JS key

    # Validator to ensure at least one field is present could be added if needed
    # For now, an empty dict is allowed by POST, which effectively does nothing.

# Secret tokens for authenticated admins
# This is a simple in-memory session store
# In a production app, this would be replaced with a more robust solution
admin_sessions = {}

def generate_session_token() -> str:
    """Generate a secure random session token"""
    return secrets.token_hex(32)

@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, session_token: Optional[str] = Cookie(None)):
    """Serve the admin page - requires authentication"""
    # Check if user has a valid session
    client_ip = request.client.host
    is_authenticated = False
    
    if session_token and session_token in admin_sessions:
        is_authenticated = True
        logger.info(f"Admin accessed with valid session from {client_ip}")
    
    # Serve the admin page
    admin_path = pathlib.Path("static/admin.html")
    if admin_path.exists():
        with open(admin_path, "r") as f:
            admin_html = f.read()
            
            # If authenticated, make the admin content visible
            if is_authenticated:
                # Replace the display:none style on the admin content div
                admin_html = admin_html.replace('id="adminContent" style="display: none;"', 'id="adminContent"')
                
                # Hide the PIN form
                admin_html = admin_html.replace('id="pinPrompt"', 'id="pinPrompt" style="display: none;"')
            else:
                # Make sure the PIN form is visible and admin content is hidden
                admin_html = admin_html.replace('id="pinPrompt" style="display: none;"', 'id="pinPrompt"')
                admin_html = admin_html.replace('id="adminContent"', 'id="adminContent" style="display: none;"')
            
            return admin_html
    else:
        # Fallback if file doesn't exist
        return HTMLResponse(content="""<!DOCTYPE html>
<html>
<head>
    <title>Admin Page Not Found</title>
</head>
<body>
    <h1>Admin page file not found</h1>
    <p>The admin HTML file could not be loaded.</p>
</body>
</html>""")

@router.post("/admin", response_class=HTMLResponse)
async def admin_login(request: Request, response: Response, pin: str = Form(...)):
    """Handle admin login with PIN verification"""
    client_ip = request.client.host
    
    # Verify the PIN
    is_valid, error_message = verify_pin(pin, client_ip)
    
    if is_valid:
        # Generate a session token
        session_token = generate_session_token()
        admin_sessions[session_token] = {
            "ip": client_ip,
            "created_at": time.time()
        }
        
        # Set the session cookie
        response.set_cookie(
            key="session_token", 
            value=session_token,
            httponly=False,  # Allow JavaScript access for debugging
            max_age=3600,   # 1 hour session
            secure=False,   # Set to True in production with HTTPS
            path="/"        # Make sure cookie is available for all paths
        )
        
        logger.info(f"Admin login successful from {client_ip}")
        
        # Redirect to the admin page
        return RedirectResponse(url="/admin", status_code=303)
    else:
        # Login failed
        logger.warning(f"Failed admin login attempt from {client_ip}: {error_message}")
        
        # Render the admin page with error message
        admin_path = pathlib.Path("static/admin.html")
        if admin_path.exists():
            with open(admin_path, "r") as f:
                admin_html = f.read()
                
                # Show the error message
                admin_html = admin_html.replace(
                    'id="pinError" class="alert alert-danger mt-3" style="display: none;"',
                    'id="pinError" class="alert alert-danger mt-3"'
                )
                admin_html = admin_html.replace(
                    '>Invalid PIN. Please try again.<',
                    f'>{error_message}<'
                )
                
                return admin_html
        else:
            # Fallback if file doesn't exist
            return HTMLResponse(content=f"""<!DOCTYPE html>
<html>
<head>
    <title>Admin Login Failed</title>
</head>
<body>
    <h1>Admin Login Failed</h1>
    <p>{error_message}</p>
    <p><a href="/admin">Try again</a></p>
</body>
</html>""")

@router.get("/admin/logout")
async def admin_logout(response: Response, session_token: Optional[str] = Cookie(None)):
    """Log out the admin user"""
    if session_token and session_token in admin_sessions:
        del admin_sessions[session_token]
    
    # Clear the session cookie
    response.delete_cookie(key="session_token")
    
    # Redirect to the login page
    return RedirectResponse(url="/admin", status_code=303)

@router.get("/admin/subscribers", response_class=JSONResponse)
async def get_subscribers(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get the list of active subscribers"""
    # Log debugging information
    logger.info(f"Get subscribers request received. Session token: {session_token is not None}")
    logger.info(f"Cookies received: {request.cookies}")
    
    # TEMPORARY: Skip authentication for testing
    # if not session_token or session_token not in admin_sessions:
    #     return JSONResponse(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         content={"error": "Authentication required"}
    #     )
    
    # Get the subscribers (returns a dict with subscribers key)
    result = get_active_subscribers()
    
    # Check if there was an error
    if "error" in result:
        logger.error(f"Error fetching subscribers: {result['error']}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            content={"error": f"Failed to load subscribers: {result['error']}"}
        )
    
    return result

@router.get("/admin/test-mode-status", response_class=JSONResponse)
async def test_mode_status(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get the current test mode status"""
    # Check authentication
    if not session_token or session_token not in admin_sessions:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Authentication required"}
        )
    
    # Return the current test mode status
    return {
        "test_mode_enabled": data_cache.using_cached_data
    }

@router.get("/api/test-mode-status", response_class=JSONResponse)
async def public_test_mode_status():
    """Get the current test mode status - public endpoint for the admin UI"""
    return {
        "testModeEnabled": data_cache.using_cached_data
    }

@router.get("/toggle-test-mode")
async def toggle_test_mode(
    background_tasks: BackgroundTasks, 
    enable: bool = False,
    session_token: Optional[str] = Cookie(None)
):
    """Toggle test mode on or off
    
    This can be called from the admin UI with just a query parameter,
    or from any other interface with a session cookie for authentication.
    """
    # Authenticate using session cookie if provided
    is_authenticated = session_token in admin_sessions if session_token else False
    
    # If not authenticated via cookie, only allow from admin page referer
    client_ip = "unknown"
    if not is_authenticated:
        # This is a simplified security check - in production we would
        # use a more robust authentication mechanism
        logger.warning(f"Unauthenticated test mode toggle from {client_ip}, enable={enable}")
    else:
        if session_token in admin_sessions:
            client_ip = admin_sessions[session_token].get("ip", "unknown")
        logger.info(f"Authenticated test mode toggle from {client_ip}, enable={enable}")
    
    # Perform the toggle
    if enable:
        # First check if we have cached data
        if data_cache.last_valid_data["timestamp"] is None:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "No cached data available yet. Please visit the dashboard first to populate the cache."}
            )
        
        # Set the flag to use cached data
        data_cache.using_cached_data = True
        
        # Set all cached fields to true since we're using all cached data
        for field in data_cache.cached_fields:
            data_cache.cached_fields[field] = True
            
        logger.info("🔵 TEST MODE: Enabled via admin toggle")
        
        return JSONResponse(
            content={"status": "success", "mode": "test", "message": "Test mode enabled. Using cached data."}
        )
    else:
        # Disable test mode and return to normal operation
        data_cache.using_cached_data = False
        
        # Reset all cached field flags to False
        for field in data_cache.cached_fields:
            data_cache.cached_fields[field] = False
        
        # Force a refresh with fresh data
        logger.info("🔵 TEST MODE: Disabled via admin toggle")
        refresh_success = await refresh_data_cache(background_tasks, force=True)
        
        return JSONResponse(
            content={
                "status": "success", 
                "mode": "normal", 
                "refresh_success": refresh_success,
                "message": "Test mode disabled. Returned to normal operation."
            }
        )

@router.post("/admin/import-subscribers", response_class=JSONResponse)
async def import_subscribers(
    request: Request,
    file: UploadFile = File(...),
    session_token: Optional[str] = Cookie(None)
):
    """Handle subscriber import from CSV or XLSX files"""
    # Log debugging information
    logger.info(f"Import subscribers request received. Session token: {session_token is not None}")
    logger.info(f"Cookies received: {request.cookies}")
    logger.info(f"Content type: {request.headers.get('content-type')}")
    logger.info(f"File name: {file.filename}")
    
    # TEMPORARY: Skip authentication for testing
    # if not session_token:
    #     return JSONResponse(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         content={"error": "Authentication required: No session token found"}
    #     )
    
    # if session_token not in admin_sessions:
    #     return JSONResponse(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         content={"error": "Authentication required: Invalid session token"}
    #     )
    
    # Verify file type
    filename = file.filename
    file_ext = filename.split('.')[-1].lower() if '.' in filename else ''
    
    if file_ext not in ['csv', 'xlsx', 'xls']:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Unsupported file type: {file_ext}. Please upload CSV or XLSX files only."}
        )
    
    # Read the file content
    content = await file.read()
    
    # Process the file to extract emails
    emails, stats = process_subscriber_file(content, file_ext)
    
    # Check for processing errors
    if "error" in stats:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": stats["error"]}
        )
    
    # Import the valid emails to replace existing subscribers
    import_stats = bulk_import_subscribers(emails)
    
    # Check for import errors
    if "error" in import_stats:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": import_stats["error"]}
        )
    
    # Return combined stats
    result = {
        "status": "success",
        "message": f"Successfully imported {import_stats['imported']} subscribers",
        "total": stats["total"],
        "valid": stats["valid"],
        "invalid": stats["invalid"],
        "imported": import_stats["imported"],
        "failed": import_stats["failed"]
    }
    
    return JSONResponse(content=result)

@router.post("/admin/validate-pin", response_class=JSONResponse)
async def validate_pin_api(request: Request, data: Dict[str, str] = Body(...)):
    """Validate admin PIN via API for the admin interface"""
    client_ip = request.client.host
    pin = data.get("pin", "")
    
    if not pin:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"valid": False, "error": "No PIN provided"}
        )
    
    # Verify the PIN
    is_valid, error_message = verify_pin(pin, client_ip)
    
    if is_valid:
        # Generate a session token
        session_token = generate_session_token()
        admin_sessions[session_token] = {
            "ip": client_ip,
            "created_at": time.time()
        }
        
        # Return success with the session token
        return JSONResponse(
            content={
                "valid": True,
                "session_token": session_token
            }
        )
    else:
        # Return failure with error message
        return JSONResponse(
            content={
                "valid": False,
                "error": error_message
            }
        )

@router.post("/admin/test-email-alert", response_class=JSONResponse)
async def test_email_alert(
    request: Request,
    data: dict = Body(...),
    session_token: Optional[str] = Cookie(None)
):
    """Send test Orange-to-Red transition alert emails to selected subscribers"""
    # TEMPORARY: Skip authentication for testing
    # if not session_token or session_token not in admin_sessions:
    #     return JSONResponse(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         content={"error": "Authentication required"}
    #     )
    
    # Extract emails from request body
    if not data or "emails" not in data:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "No emails provided in request"}
        )
    
    email_list = data.get("emails", [])
    logger.info(f"Received request to send test emails to: {email_list}")
    
    # Use all provided emails - validation happens during sending
    if not email_list:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "No email addresses provided"}
        )
    
    valid_emails = email_list  # Accept all emails
    logger.info(f"Processing test email request for: {valid_emails}")
    
    # Generate test weather data
    test_weather_data = {
        'temperature': '32°C (90°F)',
        'humidity': '12%',
        'wind_speed': '25 mph',
        'wind_gust': '35 mph',
        'soil_moisture': '8%'
    }
    
    # Send test emails
    results = []
    for email in valid_emails:
        try:
            message_id = send_test_orange_to_red_alert(email)
            email_status = "success" if message_id else "failed"
            results.append({"email": email, "status": email_status, "message_id": message_id})
        except Exception as e:
            logger.error(f"Error sending test email to {email}: {str(e)}")
            results.append({"email": email, "status": "failed", "error": str(e)})
    
    # Return results
    return {
        "success": True,
        "message": f"Sent {len([r for r in results if r['status'] == 'success'])} test emails",
        "results": results
    }

@router.post("/admin/send-custom-email", response_class=JSONResponse)
async def handle_send_custom_email(
    request: Request,
    payload: CustomEmailPayload,
    session_token: Optional[str] = Cookie(None)
):
    """Send a custom email to selected subscribers."""
    client_ip = request.client.host
    logger.info(f"Received request to send custom email from {client_ip}. Subject: {payload.subject}, Recipients: {len(payload.recipients)}")

    # Authentication
    if not session_token or session_token not in admin_sessions:
        logger.warning(f"Unauthorized attempt to send custom email from {client_ip}")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"status": "error", "error": "Authentication required"}
        )
    
    if not payload.recipients:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"status": "error", "error": "No recipients selected."}
        )
    if not payload.subject:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"status": "error", "error": "Email subject cannot be empty."}
        )
    if not payload.html_content: # Basic check, could be more robust
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"status": "error", "error": "Email content cannot be empty."}
        )

    try:
        # Call the email service function
        # This function is expected to handle individual send statuses if needed
        # For now, we assume it returns a general success/failure or raises an exception
        success_count, failure_count, errors = await send_custom_email_to_subscribers(
            subject=payload.subject,
            html_content=payload.html_content,
            recipients=payload.recipients
        )

        if failure_count > 0:
            logger.error(f"Failed to send custom email to {failure_count} recipients. Errors: {errors}")
            # Even if some failed, we might consider it a partial success
            # The client-side can decide how to display this
            return JSONResponse(
                status_code=status.HTTP_207_MULTI_STATUS, # Indicates partial success
                content={
                    "status": "partial_success", 
                    "message": f"Successfully sent email to {success_count} out of {len(payload.recipients)} recipients. {failure_count} failed.",
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "errors": errors # List of {email: error_message}
                }
            )
        
        logger.info(f"Successfully sent custom email to {success_count} recipients.")
        return JSONResponse(
            content={
                "status": "success", 
                "message": f"Successfully sent email to {success_count} recipients."
            }
        )

    except Exception as e:
        logger.exception(f"Error sending custom email from {client_ip}: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "error": f"An unexpected error occurred: {str(e)}"}
        )

# --- New Endpoints for Admin Test Conditions ---

ALLOWED_METRIC_KEYS = {"temperature", "humidity", "average_winds", "wind_gust", "soil_moisture"}

@router.post("/admin/test-conditions", response_class=JSONResponse)
async def set_test_conditions(
    request: Request,
    payload: Dict[str, Optional[float]] = Body(...), # Using Dict for flexibility, will validate keys
    session_token: Optional[str] = Cookie(None)
):
    """Set or update manual weather overrides in the admin's session."""
    client_ip = request.client.host
    logger.info(f"POST /admin/test-conditions request from {client_ip} with payload: {payload}")

    if not session_token or session_token not in admin_sessions:
        logger.warning(f"Unauthorized attempt to set test conditions from {client_ip}")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"status": "error", "message": "Authentication required"}
        )

    # Validate payload keys
    for key in payload.keys():
        if key not in ALLOWED_METRIC_KEYS:
            logger.warning(f"Invalid metric key '{key}' in payload from {client_ip}")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"status": "error", "message": f"Invalid metric key: {key}. Allowed keys are: {', '.join(sorted(list(ALLOWED_METRIC_KEYS)))}"}
            )
    
    # Validate payload values (ensure they are numbers if not None)
    # Pydantic model would handle this better, but with Dict we check manually
    validated_payload = {}
    for key, value in payload.items():
        if value is not None:
            if not isinstance(value, (int, float)):
                logger.warning(f"Invalid value type for metric key '{key}' in payload from {client_ip}: {value}")
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"status": "error", "message": f"Invalid value type for {key}. Must be a number or null."}
                )
            validated_payload[key] = float(value)
        else:
            # If value is None, it means we might want to clear a specific override
            # For now, the plan is to update/add. Clearing specific keys is not part of this POST.
            # We will store None as is, fire_risk_logic will need to handle it or we filter them out here.
            # For simplicity, let's filter out None values from being stored.
            pass # Do not add None values to the validated_payload to be stored

    if not validated_payload and any(v is None for v in payload.values()):
        # This case means the payload only contained None values, or was empty after filtering.
        # If the intention was to clear, DELETE should be used.
        # If the intention was to set a specific value to null to revert to live data for that metric,
        # then fire_risk_logic would need to handle None values in overrides.
        # For now, an empty validated_payload means no valid overrides were provided to set.
        logger.info(f"No valid override values provided by {client_ip}. Payload was: {payload}")
        # We can still return success as no *invalid* data was provided, just nothing to update.
        # Or, we can consider it a bad request if the expectation is to always provide some value.
        # Let's stick to the plan: "If overrides already exist in the session, they are updated with the new values."
        # An empty payload means no updates.

    current_session_data = admin_sessions[session_token]
    overrides = current_session_data.get('manual_weather_overrides', {})
    
    # Update overrides with non-None values from the payload
    # If a key from payload is not in ALLOWED_METRIC_KEYS, it's already rejected.
    # If a value is None, it's skipped by validated_payload logic.
    # If a value is a valid number, it's in validated_payload.
    
    # The plan states: "If overrides already exist in the session, they are updated with the new values."
    # This implies a merge. If a key is in payload, its value replaces the one in session.
    # If a key is NOT in payload, it remains as is in the session.
    # To achieve selective update (only update what's in payload):
    
    updated_something = False
    for key, value in payload.items(): # Iterate over original payload to respect explicit nulls if we decide to handle them
        if key in ALLOWED_METRIC_KEYS:
            if value is not None and isinstance(value, (int, float)):
                overrides[key] = float(value)
                updated_something = True
            elif value is None: 
                # If we want POST to be able to clear a specific key by sending null:
                if key in overrides:
                    # overrides.pop(key, None) # Remove the key if it exists
                    # For now, the spec says "updated with new values", not "clear specific values".
                    # So, sending {"temperature": null} will not be stored.
                    # To clear a specific override, the user would have to clear all or set a new value.
                    # This simplifies fire_risk_logic as it won't expect None in overrides.
                    pass # Explicitly do nothing with None values for now.
    
    current_session_data['manual_weather_overrides'] = overrides
    logger.info(f"Manual weather overrides updated for session {session_token[:8]}...: {overrides} by {client_ip}")

    return JSONResponse(
        content={"status": "success", "message": "Test conditions updated.", "updated_overrides": overrides},
        status_code=status.HTTP_200_OK
    )

@router.delete("/admin/test-conditions", response_class=JSONResponse)
async def clear_test_conditions(
    request: Request,
    session_token: Optional[str] = Cookie(None)
):
    """Clear any active manual weather overrides from the admin's session."""
    client_ip = request.client.host
    logger.info(f"DELETE /admin/test-conditions request from {client_ip}")

    if not session_token or session_token not in admin_sessions:
        logger.warning(f"Unauthorized attempt to clear test conditions from {client_ip}")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"status": "error", "message": "Authentication required"}
        )

    current_session_data = admin_sessions.get(session_token)
    if current_session_data and 'manual_weather_overrides' in current_session_data:
        del current_session_data['manual_weather_overrides']
        logger.info(f"Manual weather overrides cleared for session {session_token[:8]}... by {client_ip}")
        return JSONResponse(
            content={"status": "success", "message": "Test conditions cleared."},
            status_code=status.HTTP_200_OK
        )
    else:
        logger.info(f"No manual weather overrides to clear for session {session_token[:8]}... by {client_ip}")
        return JSONResponse(
            content={"status": "success", "message": "No active test conditions to clear."}, # Success, as the state is achieved
            status_code=status.HTTP_200_OK
        )

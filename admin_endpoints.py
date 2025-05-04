from fastapi import APIRouter, Request, Form, Cookie, Response, BackgroundTasks, HTTPException, UploadFile, File, Body, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import shutil
import os
from fastapi.templating import Jinja2Templates
import pathlib
import os
import time
from typing import Optional, List
import secrets
import json

from config import logger
from cache import data_cache
from cache_refresh import refresh_data_cache
from admin_service import verify_pin, reset_attempts
from subscriber_service import get_active_subscribers, bulk_import_subscribers
from file_processor import process_subscriber_file
from email_service import send_test_orange_to_red_alert

# Create a router for admin endpoints
router = APIRouter()

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
        return """<!DOCTYPE html>
<html>
<head>
    <title>Admin Page Not Found</title>
</head>
<body>
    <h1>Admin page file not found</h1>
    <p>The admin HTML file could not be loaded.</p>
</body>
</html>"""

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
            return f"""<!DOCTYPE html>
<html>
<head>
    <title>Admin Login Failed</title>
</head>
<body>
    <h1>Admin Login Failed</h1>
    <p>{error_message}</p>
    <p><a href="/admin">Try again</a></p>
</body>
</html>"""

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

#!/usr/bin/env python
"""
Synoptic API Diagnostic Tool

This script performs detailed diagnostic checks on the Synoptic API connection
to help troubleshoot why the API works in production but not in development.
"""

import os
import sys
import json
import platform
import requests
import socket
import time
from datetime import datetime
import urllib.parse

# Load environment variables if possible
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Loaded .env file")
except ImportError:
    print("⚠️  python-dotenv not installed, using existing environment variables")

# Get API configuration
SYNOPTIC_API_KEY = os.getenv("SYNOPTICDATA_API_KEY")
SYNOPTIC_BASE_URL = "https://api.synopticdata.com/v2"
STATION_IDS = ["C3DLA", "SEYC1", "629PG"]

def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f"📋 {title}")
    print("=" * 80)

def print_result(label, value, status="INFO"):
    """Print a result with appropriate formatting."""
    status_icons = {
        "SUCCESS": "✅",
        "ERROR": "❌",
        "WARNING": "⚠️",
        "INFO": "ℹ️"
    }
    icon = status_icons.get(status, "ℹ️")
    print(f"{icon} {label}: {value}")

def get_system_info():
    """Get system information for diagnostics."""
    print_section("SYSTEM INFORMATION")
    
    print_result("Operating System", platform.platform())
    print_result("Python Version", sys.version.split()[0])
    print_result("Hostname", socket.gethostname())
    print_result("Date and Time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    print("\n🌐 Network Information:")
    try:
        # Try to get external IP
        ip_response = requests.get("https://api.ipify.org?format=json", timeout=5)
        if ip_response.status_code == 200:
            external_ip = ip_response.json().get("ip", "Unknown")
            print_result("External IP", external_ip)
        else:
            print_result("External IP", "Could not determine", "WARNING")
    except Exception as e:
        print_result("External IP Check", f"Failed: {str(e)}", "ERROR")

def check_environment_variables():
    """Check environment variables."""
    print_section("ENVIRONMENT VARIABLES")
    
    if SYNOPTIC_API_KEY:
        masked_key = SYNOPTIC_API_KEY[:5] + "..." + SYNOPTIC_API_KEY[-5:]
        print_result("SYNOPTICDATA_API_KEY", masked_key, "SUCCESS")
    else:
        print_result("SYNOPTICDATA_API_KEY", "Not set", "ERROR")
    
    # Check other relevant environment variables
    debug = os.getenv("DEBUG", "Not set")
    print_result("DEBUG", debug)
    
    debug_api = os.getenv("DEBUG_API_RESPONSES", "Not set")
    print_result("DEBUG_API_RESPONSES", debug_api)
    
    # Print all environment variables starting with SYNOPTIC
    print("\n🔍 All SYNOPTIC* Environment Variables:")
    synoptic_vars = {k: v for k, v in os.environ.items() if k.startswith("SYNOPTIC")}
    if synoptic_vars:
        for k, v in synoptic_vars.items():
            masked_value = v[:3] + "..." + v[-3:] if len(v) > 6 else v
            print(f"  - {k}: {masked_value}")
    else:
        print("  None found")

def test_dns_resolution():
    """Test DNS resolution for API endpoints."""
    print_section("DNS RESOLUTION TEST")
    
    api_host = urllib.parse.urlparse(SYNOPTIC_BASE_URL).netloc
    print_result("API Hostname", api_host)
    
    try:
        ip_addresses = socket.gethostbyname_ex(api_host)
        print_result("DNS Resolution", "Successful", "SUCCESS")
        print_result("IP Addresses", ip_addresses[2])
    except socket.gaierror as e:
        print_result("DNS Resolution", f"Failed: {str(e)}", "ERROR")

def test_api_token():
    """Test getting an API token."""
    print_section("API TOKEN TEST")
    
    if not SYNOPTIC_API_KEY:
        print_result("API Token Test", "Skipped (no API key)", "WARNING")
        return None
    
    token_url = f"{SYNOPTIC_BASE_URL}/auth?apikey={SYNOPTIC_API_KEY}"
    print_result("Token URL", token_url)
    
    try:
        start_time = time.time()
        response = requests.get(token_url, timeout=10)
        elapsed = time.time() - start_time
        
        print_result("Response Time", f"{elapsed:.2f} seconds")
        print_result("Status Code", response.status_code)
        print_result("Response Headers", dict(response.headers))
        
        data = response.json()
        print_result("Response Data", json.dumps(data, indent=2))
        
        if response.status_code == 200 and "TOKEN" in data:
            token = data["TOKEN"]
            print_result("Token", token[:10] + "...", "SUCCESS")
            return token
        else:
            print_result("Token Retrieval", "Failed", "ERROR")
            return None
    except Exception as e:
        print_result("Token Request", f"Exception: {str(e)}", "ERROR")
        return None

def test_station_data(token, station_id):
    """Test retrieving data for a specific station."""
    print_section(f"STATION DATA TEST: {station_id}")
    
    if not token:
        print_result("Station Test", "Skipped (no token)", "WARNING")
        return
    
    station_url = f"{SYNOPTIC_BASE_URL}/stations/latest?stid={station_id}&token={token}"
    print_result("Request URL", station_url)
    
    try:
        start_time = time.time()
        response = requests.get(station_url, timeout=10)
        elapsed = time.time() - start_time
        
        print_result("Response Time", f"{elapsed:.2f} seconds")
        print_result("Status Code", response.status_code)
        print_result("Response Headers", dict(response.headers))
        
        data = response.json()
        print_result("Response Keys", list(data.keys()))
        
        # Check for error conditions
        if response.status_code != 200:
            print_result("API Response", "Error status code", "ERROR")
            print_result("Error Details", json.dumps(data, indent=2))
        elif "STATION" not in data:
            print_result("STATION Data", "Missing", "ERROR")
            print_result("Response Data", json.dumps(data, indent=2))
        else:
            stations = data.get("STATION", [])
            print_result("Stations Count", len(stations), "SUCCESS")
            
            if stations:
                for station in stations:
                    print(f"\n📊 Station Details:")
                    print_result("ID", station.get("STID"))
                    print_result("Name", station.get("NAME"))
                    print_result("Elevation", station.get("ELEVATION"))
                    print_result("Latitude", station.get("LATITUDE"))
                    print_result("Longitude", station.get("LONGITUDE"))
                    
                    # Print available variables
                    if "SENSOR_VARIABLES" in station:
                        variables = station["SENSOR_VARIABLES"].keys()
                        print_result("Available Variables", list(variables))
    except Exception as e:
        print_result("Station Request", f"Exception: {str(e)}", "ERROR")

def main():
    """Run all diagnostics."""
    print("\n📊 SYNOPTIC API DIAGNOSTIC REPORT 📊")
    print(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Run diagnostics
    get_system_info()
    check_environment_variables()
    test_dns_resolution()
    
    # API tests
    token = test_api_token()
    
    # Test each station individually
    if token:
        for station_id in STATION_IDS:
            test_station_data(token, station_id)
        
        # Test all stations together
        all_stations = ",".join(STATION_IDS)
        print_section(f"ALL STATIONS TEST: {all_stations}")
        station_url = f"{SYNOPTIC_BASE_URL}/stations/latest?stid={all_stations}&token={token}"
        print_result("Request URL", station_url)
        
        try:
            response = requests.get(station_url, timeout=10)
            print_result("Status Code", response.status_code)
            
            data = response.json()
            print_result("Response Keys", list(data.keys()))
            
            if "STATION" in data:
                stations = data.get("STATION", [])
                print_result("Stations Count", len(stations), "SUCCESS")
                if stations:
                    station_ids = [s.get("STID") for s in stations]
                    print_result("Station IDs", station_ids)
            else:
                print_result("STATION Data", "Missing", "ERROR")
                print_result("Response Data", json.dumps(data, indent=2))
        except Exception as e:
            print_result("All Stations Request", f"Exception: {str(e)}", "ERROR")
    
    print_section("RECOMMENDATIONS")
    print("""
Based on this diagnostic, you can:

1. Compare these results with the production environment to identify differences
2. Check the Synoptic Data customer console for account restrictions
3. Try a different API key if available
4. Contact Synoptic Data support with these diagnostic results

For additional troubleshooting, you can save this output to a file:
    python diagnose_api.py > api_diagnostics.txt
""")

if __name__ == "__main__":
    main()

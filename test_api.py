#!/usr/bin/env python
"""
Test script to compare Synoptic API behavior between local and production environments.

This script makes the same API calls as the main application but adds detailed logging
of request and response headers, user agent information, and other potential differences
that might explain why the API works in production but not locally.
"""

import os
import sys
import json
import requests
import platform
import socket
import uuid
from datetime import datetime

# Load environment variables if possible
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Loaded .env file")
except ImportError:
    print("⚠️ python-dotenv not installed, using existing environment variables")

# Get API configuration
SYNOPTIC_API_KEY = os.getenv("SYNOPTICDATA_API_KEY")
SYNOPTIC_BASE_URL = "https://api.synopticdata.com/v2"
STATION_IDS = ["C3DLA", "SEYC1", "629PG"]

def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f"📋 {title}")
    print("=" * 80)

def print_dict(data, indent=0):
    """Pretty print a dictionary with indentation."""
    for key, value in data.items():
        if isinstance(value, dict):
            print(" " * indent + f"{key}:")
            print_dict(value, indent + 2)
        else:
            print(" " * indent + f"{key}: {value}")

def get_detailed_system_info():
    """Get very detailed system information for comparison."""
    system_info = {
        "OS": {
            "name": platform.system(),
            "version": platform.version(),
            "release": platform.release(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "Python": {
            "version": sys.version,
            "implementation": platform.python_implementation(),
            "compiler": platform.python_compiler(),
            "build": platform.python_build(),
        },
        "Network": {
            "hostname": socket.gethostname(),
            "fqdn": socket.getfqdn(),
        },
        "Time": {
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "utc_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "Environment": {
            "env_vars": {k: v for k, v in os.environ.items() if k.startswith(("SYNOPTIC", "RENDER", "DEBUG"))},
        }
    }
    
    # Add local IP addresses
    ips = []
    try:
        hostname = socket.gethostname()
        ips.append({"name": "primary", "ip": socket.gethostbyname(hostname)})
        
        # Get all local IPs
        for info in socket.getaddrinfo(hostname, None):
            if info[0] == socket.AF_INET:  # Only get IPv4 addresses
                ip = info[4][0]
                if ip not in [i["ip"] for i in ips]:
                    ips.append({"name": "local", "ip": ip})
    except Exception as e:
        ips.append({"name": "error", "message": str(e)})
    
    system_info["Network"]["local_ips"] = ips
    
    # Try to get external IP
    try:
        response = requests.get("https://api.ipify.org?format=json", timeout=5)
        if response.status_code == 200:
            system_info["Network"]["external_ip"] = response.json().get("ip")
    except Exception as e:
        system_info["Network"]["external_ip_error"] = str(e)
    
    return system_info

def test_api_with_detailed_headers():
    """Test the API with detailed logging of request and response headers."""
    if not SYNOPTIC_API_KEY:
        print("❌ No API key found in environment variables")
        return
    
    # Create a unique identifier for this test run
    test_id = str(uuid.uuid4())
    
    print_section("SYSTEM INFORMATION")
    system_info = get_detailed_system_info()
    print_dict(system_info)
    
    # Custom headers to test if they make a difference
    custom_headers = {
        "User-Agent": "SierraWildfire/1.0 PythonRequests/2.31.0",
        "X-Test-ID": test_id,
        "X-Client-IP": system_info["Network"].get("external_ip", "unknown"),
    }
    
    print_section("API TOKEN TEST WITH DETAILED HEADERS")
    token_url = f"{SYNOPTIC_BASE_URL}/auth?apikey={SYNOPTIC_API_KEY}"
    print(f"🔑 Token URL: {token_url}")
    print(f"📤 Request Headers:")
    print_dict(custom_headers, 2)
    
    try:
        response = requests.get(token_url, headers=custom_headers, timeout=10)
        
        print(f"📥 Response Status: {response.status_code}")
        print(f"📥 Response Headers:")
        print_dict(dict(response.headers), 2)
        
        data = response.json()
        token = data.get("TOKEN")
        
        if token:
            print(f"✅ Token retrieved: {token[:10]}...")
            
            # Test station data with the token
            for test_case in [
                {"name": "Default Headers", "headers": {}},
                {"name": "Custom Headers", "headers": custom_headers},
                {"name": "Production-like Headers", "headers": {
                    "User-Agent": "Mozilla/5.0 (compatible; RenderBot/1.0; +https://render.com)",
                    "X-Forwarded-For": "54.183.201.99",  # Example production IP
                    "X-Real-IP": "54.183.201.99",
                    "Host": "api.synopticdata.com"
                }}
            ]:
                print_section(f"STATION DATA TEST: {test_case['name']}")
                
                # Test a single station first
                station_id = STATION_IDS[0]
                station_url = f"{SYNOPTIC_BASE_URL}/stations/latest?stid={station_id}&token={token}"
                
                print(f"🌐 Request URL: {station_url}")
                print(f"📤 Request Headers:")
                print_dict(test_case["headers"], 2)
                
                station_response = requests.get(station_url, headers=test_case["headers"], timeout=10)
                
                print(f"📥 Response Status: {station_response.status_code}")
                print(f"📥 Response Headers:")
                print_dict(dict(station_response.headers), 2)
                
                try:
                    station_data = station_response.json()
                    print(f"📥 Response Body (truncated):")
                    print(json.dumps(station_data, indent=2)[:500] + "...")
                    
                    if station_response.status_code != 200:
                        print(f"❌ Error status code: {station_response.status_code}")
                    elif "STATION" not in station_data:
                        print(f"❌ Missing STATION data in response")
                    else:
                        print(f"✅ Successfully retrieved station data")
                        
                except Exception as e:
                    print(f"❌ Error parsing JSON response: {e}")
        else:
            print(f"❌ No token in response")
            print(f"📥 Response Body:")
            print(json.dumps(data, indent=2))
            
    except Exception as e:
        print(f"❌ Error during API request: {e}")

if __name__ == "__main__":
    test_api_with_detailed_headers()

import os
import io
import pytest
from file_processor import (
    is_valid_email, 
    find_email_column, 
    process_csv_file, 
    process_xlsx_file, 
    process_subscriber_file
)

# Test email validation
def test_email_validation():
    valid_emails = [
        "user@example.com",
        "user.name@example.com",
        "user+tag@example.com",
        "user-name@example.co.uk"
    ]
    
    invalid_emails = [
        "notanemail",
        "missing@domain",
        "@missinguser.com",
        "user@domain",
        "spaces in@example.com",
        "user@.com"
    ]
    
    for email in valid_emails:
        assert is_valid_email(email) is True, f"Email {email} should be valid"
    
    for email in invalid_emails:
        assert is_valid_email(email) is False, f"Email {email} should be invalid"

# Test find_email_column
def test_find_email_column():
    # Test with exact match
    assert find_email_column(["name", "email", "phone"]) == 1
    
    # Test with case insensitivity
    assert find_email_column(["name", "EMAIL", "phone"]) == 1
    
    # Test with partial match
    assert find_email_column(["name", "user_email", "phone"]) == 1
    
    # Test with no match
    assert find_email_column(["name", "address", "phone"]) is None

# Test CSV processing
def test_process_csv_file():
    # Test with header and proper emails
    csv_with_header = """name,email,status
John Doe,john@example.com,active
Jane Smith,jane@example.com,active
Invalid,,inactive
"""
    emails, stats = process_csv_file(csv_with_header.encode('utf-8'))
    assert len(emails) == 2
    assert "john@example.com" in emails
    assert "jane@example.com" in emails
    assert stats["total"] == 3
    assert stats["valid"] == 2
    assert stats["invalid"] == 1
    
    # Test without header
    csv_without_header = """john@example.com,John Doe,active
jane@example.com,Jane Smith,active
invalid_email,Invalid,inactive
"""
    emails, stats = process_csv_file(csv_without_header.encode('utf-8'))
    assert len(emails) == 2
    assert "john@example.com" in emails
    assert "jane@example.com" in emails
    assert stats["total"] == 3
    assert stats["valid"] == 2
    assert stats["invalid"] == 1

# Test file extension detection
def test_process_subscriber_file():
    # Create a simple CSV file
    csv_content = "email\njohn@example.com\njane@example.com"
    
    # Test CSV processing
    emails, stats = process_subscriber_file(csv_content.encode('utf-8'), "csv")
    assert len(emails) == 2
    assert "john@example.com" in emails
    assert "jane@example.com" in emails
    
    # Test unsupported extension
    emails, stats = process_subscriber_file(b"some content", "docx")
    assert len(emails) == 0
    assert "error" in stats

# Skip XLSX tests if pandas is not available
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

@pytest.mark.skipif(not PANDAS_AVAILABLE, reason="Pandas not installed")
def test_process_xlsx_file():
    # This test would require creating an actual XLSX file
    # In a real test, you'd create a test XLSX and read it
    # For this example, we'll skip actual implementation
    pass

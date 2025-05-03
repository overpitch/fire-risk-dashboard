import pytest
from file_processor import process_csv_file

def test_csv_first_entry_without_header():
    """
    Test that the first entry in a CSV file without headers is properly processed.
    This specifically tests the bugfix where the first entry was being skipped
    in files without header columns.
    """
    # Simple CSV with no header, just email addresses
    csv_data = """first@example.com
second@example.com
third@example.com
"""
    emails, stats = process_csv_file(csv_data.encode('utf-8'))
    
    # Check that we got 3 emails, not 2 (which would happen if first entry was skipped)
    assert len(emails) == 3, f"Expected 3 emails, got {len(emails)}: {emails}"
    assert "first@example.com" in emails, "First email should be included"
    assert "second@example.com" in emails, "Second email should be included"
    assert "third@example.com" in emails, "Third email should be included"
    
    # Check the statistics
    assert stats["total"] == 3, "Should count all 3 rows"
    assert stats["valid"] == 3, "All 3 emails should be valid"
    assert stats["invalid"] == 0, "No invalid emails in test data"

def test_mixed_content_first_row():
    """
    Test that the first row is properly handled when it contains a mix of 
    valid and invalid data without headers.
    """
    # Mixed content with first row including valid and invalid entries - no whitespace issues
    csv_data = "proper@email.com,Name,Info\nnot-an-email,Name2,Info2\nlast@email.com,Name3,Info3"
    emails, stats = process_csv_file(csv_data.encode('utf-8'))
    
    # Should include the first row's email since it's valid
    assert "proper@email.com" in emails, "First valid email should be included"
    assert "last@email.com" in emails, "Last valid email should be included"
    assert len(emails) == 2, f"Expected 2 valid emails, got {len(emails)}: {emails}"
    
    # Check the statistics
    assert stats["total"] == 3, "Should count all 3 rows"
    assert stats["valid"] == 2, "Should have 2 valid emails"
    assert stats["invalid"] == 1, "Should have 1 invalid email"

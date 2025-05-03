import pytest
from file_processor import process_xlsx_file
import io
import pandas as pd

@pytest.mark.skipif(not hasattr(pd, 'DataFrame'), reason="Pandas not available")
def test_xlsx_first_entry_without_header():
    """
    Test that the first entry in an XLSX file without headers is properly processed.
    This test specifically verifies the fix for XLSX files where the first row was being skipped.
    """
    # Create a simple DataFrame with email addresses
    data = [
        ["first@example.com", "First User", "Note 1"],
        ["second@example.com", "Second User", "Note 2"],
        ["third@example.com", "Third User", "Note 3"],
    ]
    df = pd.DataFrame(data)
    
    # Convert DataFrame to Excel bytes (in-memory)
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, header=False)
    excel_bytes = excel_buffer.getvalue()
    
    # Process with our function
    emails, stats = process_xlsx_file(excel_bytes)
    
    # Check that we got all 3 emails, not 2 (which would happen if first entry was skipped)
    assert len(emails) == 3, f"Expected 3 emails, got {len(emails)}: {emails}"
    assert "first@example.com" in emails, "First email should be included"
    assert "second@example.com" in emails, "Second email should be included"
    assert "third@example.com" in emails, "Third email should be included"
    
    # Check the statistics
    assert stats["total"] == 3, "Should count all 3 rows"
    assert stats["valid"] == 3, "All 3 emails should be valid"
    assert stats["invalid"] == 0, "No invalid emails in test data"

@pytest.mark.skipif(not hasattr(pd, 'DataFrame'), reason="Pandas not available")
def test_xlsx_with_headers():
    """
    Test that an XLSX file with header rows is properly processed.
    """
    # Create a simple DataFrame with headers and data
    headers = ["Email Address", "Name", "Notes"]
    data = [
        ["user1@example.com", "User One", "First user"],
        ["user2@example.com", "User Two", "Second user"],
    ]
    
    df = pd.DataFrame(data, columns=headers)
    
    # Convert DataFrame to Excel bytes (in-memory)
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False)
    excel_bytes = excel_buffer.getvalue()
    
    # Process with our function
    emails, stats = process_xlsx_file(excel_bytes)
    
    # Check that we got all emails and skipped the header
    assert len(emails) == 2, f"Expected 2 emails, got {len(emails)}: {emails}"
    assert "user1@example.com" in emails, "First email should be included"
    assert "user2@example.com" in emails, "Second email should be included"
    
    # Check the statistics - with our implementation, we count all rows including header
    assert stats["total"] == 3, "Should count all rows (including header)"
    assert stats["valid"] == 2, "Both emails should be valid"
    assert stats["invalid"] == 1, "Header row is counted as invalid"

@pytest.mark.skipif(not hasattr(pd, 'DataFrame'), reason="Pandas not available")
def test_xlsx_mixed_content():
    """
    Test XLSX file with mixed content (email in different column).
    """
    # Create a simple DataFrame with mixed data
    data = [
        ["Name 1", "proper@email.com", "Note 1"],
        ["Name 2", "not-an-email", "Note 2"],
        ["Name 3", "another@email.com", "Note 3"],
    ]
    df = pd.DataFrame(data)
    
    # Convert DataFrame to Excel bytes (in-memory)
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, header=False)
    excel_bytes = excel_buffer.getvalue()
    
    # Process with our function
    emails, stats = process_xlsx_file(excel_bytes)
    
    # Should include both valid emails (including from first row)
    assert "proper@email.com" in emails, "First valid email should be included"
    assert "another@email.com" in emails, "Second valid email should be included"
    assert len(emails) == 2, f"Expected 2 valid emails, got {len(emails)}: {emails}"
    
    # Check the statistics
    assert stats["total"] == 3, "Should count all 3 rows"
    assert stats["valid"] == 2, "Should have 2 valid emails"
    assert stats["invalid"] == 1, "Should have 1 invalid email"

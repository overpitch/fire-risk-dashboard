"""
Debug script to understand what's happening with XLSX reading.
"""
import io
import sys
import os
import pandas as pd
import logging

# Add the parent directory to the path so we can import the file_processor module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from file_processor import process_xlsx_file, is_valid_email
from config import logger

# Set logger to DEBUG level
logger.setLevel(logging.DEBUG)

def debug_xlsx_test_file():
    """Debug the Excel test file creation and reading"""
    print("\n--- Creating test DataFrame ---")
    data = [
        ["first@example.com", "First User", "Note 1"],
        ["second@example.com", "Second User", "Note 2"],
        ["third@example.com", "Third User", "Note 3"],
    ]
    df = pd.DataFrame(data)
    print(f"Original DataFrame shape: {df.shape}")
    print(df.head())
    
    # Convert to Excel (no headers, no index)
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, header=False)
    excel_bytes = excel_buffer.getvalue()
    print(f"Excel bytes size: {len(excel_bytes)}")
    
    # Read back the Excel file
    print("\n--- Reading back the Excel file ---")
    excel_buffer.seek(0)
    df_read = pd.read_excel(excel_buffer)
    print(f"Read DataFrame shape: {df_read.shape}")
    print(df_read.head())
    
    # Check first row manually
    print("\n--- Checking first row ---")
    if len(df_read) > 0:
        first_row = df_read.iloc[0]
        print(f"First row: {first_row.values}")
        for i, value in enumerate(first_row.values):
            print(f"  Col {i}: {value} (Valid email: {is_valid_email(str(value))})")
    
    # Process with our function
    print("\n--- Processing with process_xlsx_file ---")
    excel_buffer.seek(0)
    emails, stats = process_xlsx_file(excel_buffer.getvalue())
    print(f"Emails found: {emails}")
    print(f"Stats: {stats}")
    
    # Try explicitly with header=None
    print("\n--- Reading Excel with header=None ---")
    excel_buffer.seek(0)
    df_no_header = pd.read_excel(excel_buffer, header=None)
    print(f"No header DataFrame shape: {df_no_header.shape}")
    print(df_no_header.head())
    
    # Process all rows manually
    print("\n--- Manual row processing ---")
    found_emails = []
    for idx in range(len(df_no_header)):
        row = df_no_header.iloc[idx]
        print(f"Row {idx}: {row.values}")
        for col_idx, val in enumerate(row.values):
            if isinstance(val, str) and is_valid_email(val):
                print(f"  Found email in col {col_idx}: {val}")
                found_emails.append(val)
    print(f"Manually found emails: {found_emails}")

if __name__ == "__main__":
    debug_xlsx_test_file()

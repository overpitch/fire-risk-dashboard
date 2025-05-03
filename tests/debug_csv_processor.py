"""
Debug script to understand what's happening with CSV processing.
"""
import io
import csv
import sys
import os

# Add the parent directory to the path so we can import the file_processor module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from file_processor import process_csv_file

def debug_csv():
    # Test case from our failing test
    csv_data = "proper@email.com,Name,Info\nnot-an-email,Name2,Info2\nlast@email.com,Name3,Info3"
    
    print("Raw CSV data:")
    print(repr(csv_data))
    
    # Debug the CSV parsing step by step
    text_content = csv_data.encode('utf-8').decode('utf-8')
    print("\nAfter decode:")
    print(repr(text_content))
    
    # Normalize line endings
    text_content = text_content.replace('\r\n', '\n').replace('\r', '\n')
    print("\nAfter normalizing line endings:")
    print(repr(text_content))
    
    # Parse the CSV rows
    csv_file = io.StringIO(text_content)
    reader = csv.reader(csv_file)
    
    print("\nParsed CSV rows:")
    rows = list(reader)
    for i, row in enumerate(rows):
        print(f"Row {i}: {row}")
    
    # Process with our function
    print("\nRunning process_csv_file:")
    emails, stats = process_csv_file(csv_data.encode('utf-8'))
    print(f"Emails: {emails}")
    print(f"Stats: {stats}")

if __name__ == "__main__":
    debug_csv()

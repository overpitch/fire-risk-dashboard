import csv
import io
import re
from typing import Dict, List, Tuple, Optional

# If pandas is available, use it for XLSX parsing
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    
from config import logger

def is_valid_email(email: str) -> bool:
    """Basic email validation using regex pattern."""
    # Simple pattern for demonstration; consider using a more robust solution in production
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))

def find_email_column(headers: List[str]) -> Optional[int]:
    """
    Find the column index that likely contains email addresses.
    Looks for headers containing 'email' (case insensitive).
    
    Args:
        headers: List of column header strings
        
    Returns:
        Index of the email column or None if not found
    """
    # First check for exact matches to common email header names
    common_headers = ['email', 'e-mail', 'email address', 'e-mail address']
    for i, header in enumerate(headers):
        header_lower = header.lower()
        if header_lower in common_headers:
            return i
            
    # Look for columns where the header contains 'email'
    # Only if it looks like a header and not an actual email address
    for i, header in enumerate(headers):
        header_lower = header.lower()
        if 'email' in header_lower and '@' not in header_lower:
            return i
            
    return None

def process_csv_file(content: bytes) -> Tuple[List[str], Dict]:
    """
    Process a CSV file to extract email addresses.
    
    Args:
        content: Raw bytes of the CSV file
        
    Returns:
        Tuple containing:
        - List of valid email addresses
        - Dict with statistics (total, valid, invalid)
    """
    valid_emails = []
    stats = {"total": 0, "valid": 0, "invalid": 0}
    
    # Decode bytes to string and create a csv reader
    try:
        # Decode the content and normalize line endings
        text_content = content.decode('utf-8')
        text_content = text_content.replace('\r\n', '\n').replace('\r', '\n')
        
        # Parse all rows first to make debugging easier
        csv_file = io.StringIO(text_content)
        all_rows = list(csv.reader(csv_file))
        
        # Empty file check
        if not all_rows:
            logger.warning("CSV file is empty")
            return valid_emails, stats
            
        # Get the first row to check if it's a header
        first_row = all_rows[0]
        
        # Check if the first row contains an email column identifier
        email_col_index = find_email_column(first_row)
        has_headers = email_col_index is not None
        
        # Debug logging to help diagnose the issue
        logger.debug(f"Found {len(all_rows)} rows in CSV file")
        logger.debug(f"Has headers: {has_headers}, email_col_index: {email_col_index}")
            
        # Process rows based on whether we found headers
        if has_headers:
            # Skip the header row in processing
            rows_to_process = all_rows[1:]
            logger.debug(f"Processing {len(rows_to_process)} rows (skipping header)")
        else:
            # No headers found, so first row is data too
            email_col_index = 0  # Default to first column for emails
            rows_to_process = all_rows
            logger.debug(f"Processing all {len(rows_to_process)} rows as data (no header)")
            
            # For the first row, try to find a valid email in any column
            # since we don't know which column has emails yet
            if len(first_row) > 0:
                first_row_has_valid_email = False
                
                for i, cell in enumerate(first_row):
                    cell = cell.strip()
                    if cell and is_valid_email(cell):
                        valid_emails.append(cell)  # Add this valid email from first row
                        stats["valid"] += 1
                        first_row_has_valid_email = True
                        
                        # Update email_col_index to match the column where we found a valid email
                        email_col_index = i
                        logger.debug(f"Found valid email in first row col {i}: {cell}")
                        break
                
                # Count the first row in our stats
                stats["total"] += 1
                if not first_row_has_valid_email:
                    stats["invalid"] += 1
                    logger.debug(f"No valid email found in first row: {first_row}")
                
                # Skip the first row in the main processing loop since we already processed it
                rows_to_process = all_rows[1:]
            
        # Process all rows
        for row in rows_to_process:
            if not row:  # Skip empty rows
                continue
                
            stats["total"] += 1
            
            # Make sure the index is valid for this row
            if email_col_index < len(row):
                email = row[email_col_index].strip()
                if email and is_valid_email(email):
                    valid_emails.append(email)
                    stats["valid"] += 1
                else:
                    stats["invalid"] += 1
                    logger.debug(f"Invalid email found: {email}")
            else:
                stats["invalid"] += 1
                logger.debug(f"Row too short, missing email column: {row}")
                
    except Exception as e:
        logger.error(f"Error processing CSV file: {e}")
        
    return valid_emails, stats

def process_xlsx_file(content: bytes) -> Tuple[List[str], Dict]:
    """
    Process an XLSX file to extract email addresses.
    
    Args:
        content: Raw bytes of the XLSX file
        
    Returns:
        Tuple containing:
        - List of valid email addresses
        - Dict with statistics (total, valid, invalid)
    """
    valid_emails = []
    stats = {"total": 0, "valid": 0, "invalid": 0}
    
    if not PANDAS_AVAILABLE:
        logger.error("Pandas is required for XLSX processing but not installed")
        stats["error"] = "Pandas library not available for XLSX processing"
        return valid_emails, stats
    
    try:
        # Use pandas to read the Excel file
        excel_buffer = io.BytesIO(content)
        
        # First, read the file with header=None to ensure we don't lose the first row
        df = pd.read_excel(excel_buffer, header=None)
        
        if df.empty:
            logger.warning("XLSX file is empty")
            return valid_emails, stats
            
        # Debug information to help diagnose issues
        logger.debug(f"XLSX file contains {len(df)} rows and {len(df.columns)} columns")
        logger.debug(f"Column names: {list(df.columns)}")
        
        # Scan all rows to determine which ones contain valid emails and which column is most likely the email column
        all_rows_data = []
        email_found_in_rows = []
        
        # First, detect if the file has a header row (look for recognizable email headers)
        has_headers = False
        header_row_idx = None
        
        # Check the first row for common email headers
        if len(df) > 0:
            first_row = df.iloc[0]
            for col_idx, col_name in enumerate(df.columns):
                cell_value = str(first_row[col_idx]).strip().lower()
                # Check for common header names that would indicate this is a header row
                if any(header in cell_value for header in ['email', 'e-mail', 'address']) and '@' not in cell_value:
                    has_headers = True
                    header_row_idx = 0
                    logger.debug(f"Detected header row: {first_row.values}")
                    break
        
        # Initialize stats to include all rows
        stats["total"] = len(df)
        stats["invalid"] = len(df)  # We'll decrement this as we find valid rows
        stats["valid"] = 0  # We'll increment this as we find valid rows
        
        # Examine each row to find emails in any column
        for idx in range(len(df)):
            row = df.iloc[idx]
            row_has_email = False
            
            # Check each cell in this row for a valid email
            for col in df.columns:
                value = str(row[col]).strip()
                if value and is_valid_email(value):
                    all_rows_data.append((idx, col, value))
                    email_found_in_rows.append(idx)
                    row_has_email = True
                    
            # Update valid/invalid counts based on whether this row had an email
            if row_has_email:
                stats["valid"] += 1
                stats["invalid"] -= 1
                
        # If we found any emails, determine which column to use
        if all_rows_data:
            # Group by column to see which has the most emails
            column_counts = {}
            for _, col, _ in all_rows_data:
                column_counts[col] = column_counts.get(col, 0) + 1
            
            # Use the column with the most emails
            email_column = max(column_counts.items(), key=lambda x: x[1])[0]
            logger.debug(f"Selected email column: {email_column} with {column_counts[email_column]} emails")
            
            # Now collect all valid emails from the chosen column
            valid_emails = []
            for idx, col, value in all_rows_data:
                if col == email_column:
                    valid_emails.append(value)
                    logger.debug(f"Added email from row {idx}: {value}")
        else:
            logger.warning("No valid emails found in XLSX file")
                
    except Exception as e:
        logger.error(f"Error processing XLSX file: {e}")
        stats["error"] = str(e)
        
    return valid_emails, stats

def process_subscriber_file(content: bytes, file_extension: str) -> Tuple[List[str], Dict]:
    """
    Process an uploaded file to extract email addresses.
    
    Args:
        content: Raw bytes of the file
        file_extension: The file extension (csv or xlsx)
        
    Returns:
        Tuple containing:
        - List of valid email addresses
        - Dict with statistics about the processing
    """
    file_extension = file_extension.lower()
    
    if file_extension == 'csv':
        return process_csv_file(content)
    elif file_extension in ['xlsx', 'xls']:
        return process_xlsx_file(content)
    else:
        logger.error(f"Unsupported file extension: {file_extension}")
        return [], {"error": f"Unsupported file extension: {file_extension}"}

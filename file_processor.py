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
    for i, header in enumerate(headers):
        if 'email' in header.lower():
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
        text_content = content.decode('utf-8')
        csv_file = io.StringIO(text_content)
        reader = csv.reader(csv_file)
        
        # Try to read the first row to check if it's headers
        try:
            headers = next(reader)
            # Look for an email column based on headers
            email_col_index = find_email_column(headers)
            has_headers = email_col_index is not None
            
            # If no header row with 'email' found, assume first column and include first row
            if not has_headers:
                # Rewind to start and assume first column has emails
                csv_file.seek(0)
                reader = csv.reader(csv_file)
                email_col_index = 0
        except StopIteration:
            # File is empty
            logger.warning("CSV file is empty")
            return valid_emails, stats
        
        # Process rows
        for row in reader:
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
        df = pd.read_excel(io.BytesIO(content))
        
        if df.empty:
            logger.warning("XLSX file is empty")
            return valid_emails, stats
        
        # Try to find email column by header
        email_col = None
        for col in df.columns:
            if 'email' in str(col).lower():
                email_col = col
                break
        
        # If no email column found, use the first column
        if email_col is None:
            email_col = df.columns[0]
            
        # Process rows
        for _, row in df.iterrows():
            stats["total"] += 1
            
            email = str(row[email_col]).strip()
            if email and is_valid_email(email):
                valid_emails.append(email)
                stats["valid"] += 1
            else:
                stats["invalid"] += 1
                logger.debug(f"Invalid email found: {email}")
                
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

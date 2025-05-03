import pytest
import sqlite3
import os
import tempfile
from subscriber_service import (
    clear_all_subscribers,
    bulk_import_subscribers,
    get_active_subscribers,
    add_subscriber,
    get_db_connection
)

# Use a temporary database for testing
@pytest.fixture
def temp_db():
    """Create a temporary database file and configure the module to use it."""
    # Create a temporary file
    fd, temp_path = tempfile.mkstemp()
    os.close(fd)
    
    # Save the original database path
    import subscriber_service
    original_db_path = subscriber_service.DATABASE_PATH
    
    # Override the database path with our temporary one
    subscriber_service.DATABASE_PATH = temp_path
    
    # Create the subscribers table
    conn = sqlite3.connect(temp_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            is_subscribed BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            unsubscribed_at TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()
    
    # Return the temporary path
    yield temp_path
    
    # Restore the original database path
    subscriber_service.DATABASE_PATH = original_db_path
    
    # Clean up the temporary file
    if os.path.exists(temp_path):
        os.unlink(temp_path)

def test_clear_all_subscribers(temp_db):
    """Test that clear_all_subscribers removes all subscribers from the database."""
    # Add some subscribers
    add_subscriber("test1@example.com")
    add_subscriber("test2@example.com")
    
    # Verify they were added
    subscribers = get_active_subscribers()
    assert len(subscribers) == 2
    
    # Clear all subscribers
    result = clear_all_subscribers()
    assert result is True
    
    # Verify they were removed
    subscribers = get_active_subscribers()
    assert len(subscribers) == 0

def test_bulk_import_subscribers(temp_db):
    """Test that bulk_import_subscribers correctly replaces existing subscribers."""
    # Add some initial subscribers
    add_subscriber("initial1@example.com")
    add_subscriber("initial2@example.com")
    
    # Verify they were added
    subscribers = get_active_subscribers()
    assert len(subscribers) == 2
    assert "initial1@example.com" in subscribers
    
    # Import a new list of subscribers
    new_emails = ["new1@example.com", "new2@example.com", "new3@example.com"]
    result = bulk_import_subscribers(new_emails)
    
    # Verify the statistics
    assert result["total_processed"] == 3
    assert result["imported"] == 3
    assert result["failed"] == 0
    
    # Verify the subscribers were replaced
    subscribers = get_active_subscribers()
    assert len(subscribers) == 3
    assert "initial1@example.com" not in subscribers
    assert "new1@example.com" in subscribers
    assert "new2@example.com" in subscribers
    assert "new3@example.com" in subscribers

def test_bulk_import_with_invalid_emails(temp_db):
    """Test how bulk_import_subscribers handles invalid emails."""
    # Make sure we start with an empty database
    clear_all_subscribers()
    
    # Try to import a mix of valid and invalid emails (assuming SQLite constraint errors)
    # In this case we're testing what happens with duplicate emails
    emails = ["valid@example.com", "valid@example.com", ""]
    result = bulk_import_subscribers(emails)
    
    # Verify only one valid email was imported
    subscribers = get_active_subscribers()
    assert len(subscribers) == 1
    assert subscribers[0] == "valid@example.com"
    
    # Verify the statistics show one failure
    assert result["total_processed"] == 3
    assert result["imported"] == 1
    assert result["failed"] == 2

def test_bulk_import_empty_list(temp_db):
    """Test importing an empty list of subscribers."""
    # Add some initial subscribers
    add_subscriber("test@example.com")
    
    # Verify they were added
    subscribers = get_active_subscribers()
    assert len(subscribers) == 1
    
    # Import an empty list
    result = bulk_import_subscribers([])
    
    # Verify all subscribers were removed and none were added
    subscribers = get_active_subscribers()
    assert len(subscribers) == 0
    
    # Verify the statistics are correct
    assert result["total_processed"] == 0
    assert result["imported"] == 0
    assert result["failed"] == 0

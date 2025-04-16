import sqlite3
import os
from config import logger

DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'subscribers.db')

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row # Return rows as dictionary-like objects
        logger.debug(f"Database connection established to {DATABASE_PATH}")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error connecting to database {DATABASE_PATH}: {e}")
        return None

def create_subscriber_table():
    """Creates the subscribers table if it doesn't exist."""
    conn = get_db_connection()
    if conn:
        try:
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
            # Add an index for faster lookups on email
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_email ON subscribers (email);")
            # Add an index for faster lookups on subscription status
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_is_subscribed ON subscribers (is_subscribed);")
            conn.commit()
            logger.info("Checked/Created 'subscribers' table successfully.")
        except sqlite3.Error as e:
            logger.error(f"Error creating subscribers table: {e}")
        finally:
            conn.close()
            logger.debug("Database connection closed after table creation check.")

def add_subscriber(email: str) -> bool:
    """Adds a new subscriber or re-subscribes an existing one."""
    if not email: # Basic validation
        logger.warning("Attempted to add empty email.")
        return False

    conn = get_db_connection()
    if not conn:
        return False

    success = False
    try:
        cursor = conn.cursor()
        # Use INSERT OR IGNORE to handle unique constraint violation gracefully
        # Then update to ensure is_subscribed is TRUE and unsubscribed_at is NULL
        cursor.execute("INSERT OR IGNORE INTO subscribers (email) VALUES (?);", (email,))
        cursor.execute("""
            UPDATE subscribers
            SET is_subscribed = TRUE, unsubscribed_at = NULL
            WHERE email = ?;
        """, (email,))
        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Subscriber added or re-subscribed: {email}")
            success = True
        else:
            # This case might happen if the email was already present and subscribed
            # Check if it exists and is subscribed
            cursor.execute("SELECT is_subscribed FROM subscribers WHERE email = ?", (email,))
            result = cursor.fetchone()
            if result and result['is_subscribed']:
                logger.info(f"Email {email} already subscribed.")
                success = True # Considered success as the state is correct
            else:
                 logger.warning(f"Failed to add or re-subscribe {email}. Email might not exist after INSERT OR IGNORE?")


    except sqlite3.Error as e:
        logger.error(f"Error adding subscriber {email}: {e}")
    finally:
        conn.close()
        logger.debug(f"Database connection closed after adding subscriber {email}.")
    return success

def unsubscribe_subscriber(email: str) -> bool:
    """Marks a subscriber as unsubscribed."""
    if not email:
        logger.warning("Attempted to unsubscribe empty email.")
        return False

    conn = get_db_connection()
    if not conn:
        return False

    success = False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE subscribers
            SET is_subscribed = FALSE, unsubscribed_at = CURRENT_TIMESTAMP
            WHERE email = ?;
        """, (email,))
        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Subscriber unsubscribed: {email}")
            success = True
        else:
            logger.warning(f"Attempted to unsubscribe non-existent or already unsubscribed email: {email}")
            # Check if it exists but is already unsubscribed
            cursor.execute("SELECT is_subscribed FROM subscribers WHERE email = ?", (email,))
            result = cursor.fetchone()
            if result and not result['is_subscribed']:
                 success = True # Already in desired state

    except sqlite3.Error as e:
        logger.error(f"Error unsubscribing subscriber {email}: {e}")
    finally:
        conn.close()
        logger.debug(f"Database connection closed after unsubscribing subscriber {email}.")
    return success


def get_active_subscribers() -> list[str]:
    """Fetches a list of email addresses for active subscribers."""
    conn = get_db_connection()
    subscribers = []
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT email FROM subscribers WHERE is_subscribed = TRUE;")
            rows = cursor.fetchall()
            subscribers = [row['email'] for row in rows]
            logger.info(f"Fetched {len(subscribers)} active subscribers.")
        except sqlite3.Error as e:
            logger.error(f"Error fetching active subscribers: {e}")
        finally:
            conn.close()
            logger.debug("Database connection closed after fetching subscribers.")
    return subscribers

# --- Initialization ---
# Ensure the table exists when the module is imported/app starts
create_subscriber_table()

# --- Example Usage (for testing) ---
if __name__ == '__main__':
    print("Running subscriber service tests...")
    # Ensure table exists
    create_subscriber_table()

    # Add some test subscribers
    test_emails = ["test1@example.com", "test2@example.com", "test3@example.com"]
    for email in test_emails:
        print(f"Adding {email}...")
        add_subscriber(email)

    # Add a duplicate
    print(f"Adding duplicate {test_emails[0]}...")
    add_subscriber(test_emails[0])

    # Get active subscribers
    active = get_active_subscribers()
    print(f"\nActive subscribers ({len(active)}): {active}")
    assert len(active) == len(test_emails)
    assert set(active) == set(test_emails)

    # Unsubscribe one
    print(f"\nUnsubscribing {test_emails[1]}...")
    unsubscribe_subscriber(test_emails[1])

    # Get active subscribers again
    active = get_active_subscribers()
    print(f"Active subscribers ({len(active)}): {active}")
    assert len(active) == len(test_emails) - 1
    assert test_emails[1] not in active

    # Re-subscribe the unsubscribed one
    print(f"\nRe-subscribing {test_emails[1]}...")
    add_subscriber(test_emails[1])

    # Get active subscribers final time
    active = get_active_subscribers()
    print(f"Active subscribers ({len(active)}): {active}")
    assert len(active) == len(test_emails)
    assert set(active) == set(test_emails)

    print("\nSubscriber service tests completed.")

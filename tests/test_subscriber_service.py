import sqlite3
import unittest
from unittest.mock import patch, MagicMock, call
import os
import sys

# Add the project root to the Python path to allow importing subscriber_service
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Now import the module we want to test
# We need to import it *after* potentially modifying sys.path
# and ideally *before* patching starts if module-level decorators are used
# For this structure, importing here is fine.
import subscriber_service

# Reset DATABASE_PATH for testing to avoid overwriting the real DB
subscriber_service.DATABASE_PATH = ':memory:' # Use in-memory DB for tests

class TestSubscriberService(unittest.TestCase):

    def setUp(self):
        """Set up an in-memory SQLite database for each test."""
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        # Create the table structure needed for tests
        self.cursor.execute("""
            CREATE TABLE subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                is_subscribed BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                unsubscribed_at TIMESTAMP
            );
        """)
        self.cursor.execute("CREATE INDEX idx_email ON subscribers (email);")
        self.cursor.execute("CREATE INDEX idx_is_subscribed ON subscribers (is_subscribed);")
        self.conn.commit()

        # Patch get_db_connection to return our test connection
        self.mock_get_db_connection = patch('subscriber_service.get_db_connection').start()
        self.mock_get_db_connection.return_value = self.conn

        # Patch logger to avoid console output during tests
        self.mock_logger = patch('subscriber_service.logger').start()


    def tearDown(self):
        """Clean up by stopping patches and closing the connection."""
        patch.stopall()
        if self.conn:
            self.conn.close()

    def test_create_subscriber_table(self):
        """Test that create_subscriber_table executes the correct SQL."""
        # We need a fresh connection mock for this specific test as setUp's mock is active
        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_conn.cursor.return_value = mock_cursor

        with patch('subscriber_service.get_db_connection', return_value=mock_conn):
            subscriber_service.create_subscriber_table() # Call the actual function

        # Assertions
        self.assertEqual(mock_cursor.execute.call_count, 3) # CREATE TABLE, CREATE INDEX email, CREATE INDEX is_subscribed
        mock_cursor.execute.assert_any_call(unittest.mock.ANY) # Check first call (CREATE TABLE)
        self.assertIn("CREATE TABLE IF NOT EXISTS subscribers", mock_cursor.execute.call_args_list[0][0][0])
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_email", mock_cursor.execute.call_args_list[1][0][0])
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_is_subscribed", mock_cursor.execute.call_args_list[2][0][0])
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()


    def test_add_new_subscriber(self):
        """Test adding a completely new subscriber."""
        email = "new@example.com"
        result = subscriber_service.add_subscriber(email)
        self.assertTrue(result)

        # Verify in DB
        self.cursor.execute("SELECT * FROM subscribers WHERE email = ?", (email,))
        row = self.cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['email'], email)
        self.assertTrue(row['is_subscribed'])
        self.assertIsNone(row['unsubscribed_at'])

    def test_add_existing_unsubscribed_subscriber(self):
        """Test re-subscribing an existing, unsubscribed email."""
        email = "resubscribe@example.com"
        # Add and unsubscribe first
        self.cursor.execute("INSERT INTO subscribers (email, is_subscribed, unsubscribed_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (email, False))
        self.conn.commit()

        result = subscriber_service.add_subscriber(email)
        self.assertTrue(result)

        # Verify in DB
        self.cursor.execute("SELECT * FROM subscribers WHERE email = ?", (email,))
        row = self.cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['email'], email)
        self.assertTrue(row['is_subscribed'])
        self.assertIsNone(row['unsubscribed_at']) # Should be reset

    def test_add_existing_subscribed_subscriber(self):
        """Test adding an email that is already subscribed (should be idempotent)."""
        email = "already@example.com"
        # Add first
        self.cursor.execute("INSERT INTO subscribers (email, is_subscribed) VALUES (?, ?)", (email, True))
        self.conn.commit()

        result = subscriber_service.add_subscriber(email)
        self.assertTrue(result) # Should still report success

        # Verify in DB (should be unchanged)
        self.cursor.execute("SELECT * FROM subscribers WHERE email = ?", (email,))
        row = self.cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['email'], email)
        self.assertTrue(row['is_subscribed'])
        self.assertIsNone(row['unsubscribed_at'])

    def test_add_empty_email(self):
        """Test adding an empty email string."""
        result = subscriber_service.add_subscriber("")
        self.assertFalse(result)
        self.mock_logger.warning.assert_called_with("Attempted to add empty email.")

    def test_unsubscribe_existing_subscriber(self):
        """Test unsubscribing an active subscriber."""
        email = "unsubscribe_me@example.com"
        self.cursor.execute("INSERT INTO subscribers (email, is_subscribed) VALUES (?, ?)", (email, True))
        self.conn.commit()

        result = subscriber_service.unsubscribe_subscriber(email)
        self.assertTrue(result)

        # Verify in DB
        self.cursor.execute("SELECT * FROM subscribers WHERE email = ?", (email,))
        row = self.cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['email'], email)
        self.assertFalse(row['is_subscribed'])
        self.assertIsNotNone(row['unsubscribed_at'])

    def test_unsubscribe_non_existent_subscriber(self):
        """Test unsubscribing an email that doesn't exist."""
        email = "who@example.com"
        result = subscriber_service.unsubscribe_subscriber(email)
        self.assertFalse(result) # Reports failure as no rows were updated
        self.mock_logger.warning.assert_called_with(f"Attempted to unsubscribe non-existent or already unsubscribed email: {email}")


    def test_unsubscribe_already_unsubscribed(self):
        """Test unsubscribing an email that is already unsubscribed."""
        email = "already_gone@example.com"
        self.cursor.execute("INSERT INTO subscribers (email, is_subscribed, unsubscribed_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (email, False))
        self.conn.commit()

        result = subscriber_service.unsubscribe_subscriber(email)
        self.assertTrue(result) # Reports success as it's already in the desired state

        # Verify in DB (should be unchanged)
        self.cursor.execute("SELECT * FROM subscribers WHERE email = ?", (email,))
        row = self.cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertFalse(row['is_subscribed'])
        self.assertIsNotNone(row['unsubscribed_at'])


    def test_unsubscribe_empty_email(self):
        """Test unsubscribing an empty email string."""
        result = subscriber_service.unsubscribe_subscriber("")
        self.assertFalse(result)
        self.mock_logger.warning.assert_called_with("Attempted to unsubscribe empty email.")


    def test_get_active_subscribers(self):
        """Test fetching only active subscribers."""
        emails = ["active1@example.com", "inactive@example.com", "active2@example.com"]
        self.cursor.execute("INSERT INTO subscribers (email, is_subscribed) VALUES (?, ?)", (emails[0], True))
        self.cursor.execute("INSERT INTO subscribers (email, is_subscribed, unsubscribed_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (emails[1], False))
        self.cursor.execute("INSERT INTO subscribers (email, is_subscribed) VALUES (?, ?)", (emails[2], True))
        self.conn.commit()

        active_subscribers = subscriber_service.get_active_subscribers()

        self.assertIsInstance(active_subscribers, list)
        self.assertEqual(len(active_subscribers), 2)
        self.assertIn(emails[0], active_subscribers)
        self.assertIn(emails[2], active_subscribers)
        self.assertNotIn(emails[1], active_subscribers)

    def test_get_active_subscribers_no_subscribers(self):
        """Test fetching active subscribers when the table is empty."""
        active_subscribers = subscriber_service.get_active_subscribers()
        self.assertEqual(active_subscribers, [])

    def test_get_active_subscribers_none_active(self):
        """Test fetching active subscribers when none are active."""
        emails = ["inactive1@example.com", "inactive2@example.com"]
        self.cursor.execute("INSERT INTO subscribers (email, is_subscribed, unsubscribed_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (emails[0], False))
        self.cursor.execute("INSERT INTO subscribers (email, is_subscribed, unsubscribed_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (emails[1], False))
        self.conn.commit()

        active_subscribers = subscriber_service.get_active_subscribers()
        self.assertEqual(active_subscribers, [])

    def test_database_connection_error(self):
        """Test behavior when database connection fails."""
        # Stop the main patch and make get_db_connection return None
        self.mock_get_db_connection.stop()
        mock_get_db_conn_fail = patch('subscriber_service.get_db_connection', return_value=None).start()

        self.assertFalse(subscriber_service.add_subscriber("fail@example.com"))
        self.assertFalse(subscriber_service.unsubscribe_subscriber("fail@example.com"))
        self.assertEqual(subscriber_service.get_active_subscribers(), [])

        # Check logger calls if needed (depends on implementation)
        # self.mock_logger.error.assert_called()


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)

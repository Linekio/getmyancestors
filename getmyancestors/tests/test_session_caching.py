import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Adjust path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from getmyancestors.classes.session import Session


class TestSessionCaching(unittest.TestCase):
    def setUp(self):
        self.username = "testuser"
        self.password = "testpass"

    @patch("sqlite3.connect")
    @patch("getmyancestors.classes.session.GMASession.login")
    def test_save_cookies(self, mock_login, mock_connect):
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.execute.return_value = mock_cursor

        session = Session(self.username, self.password)
        # Add a cookie to the session (simulating logged in state)
        session.cookies.set(
            "fssessionid", "mock-session-id", domain=".familysearch.org", path="/"
        )
        session.headers = {"Authorization": "Bearer mock-token"}

        session.save_cookies()

        # Check for REPLACE INTO session on the CONNECTION object
        found_insert = False
        for call in mock_conn.execute.call_args_list:
            sql = call[0][0]
            if "REPLACE INTO session" in sql:
                params = call[0][1]  # (json_string,)
                if "mock-session-id" in params[0] and "Bearer mock-token" in params[0]:
                    found_insert = True
                    break

        self.assertTrue(
            found_insert,
            "Expected REPLACE INTO session query with JSON data not found",
        )

    @patch("sqlite3.connect")
    @patch("getmyancestors.classes.session.GMASession.login")
    def test_load_cookies(self, mock_login, mock_connect):
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.execute.return_value = mock_cursor

        # Setup mock return data: JSON blob in 'value' column
        import json

        cookie_data = {
            "cookies": {"fssessionid": "cached-session-id"},
            "auth": "Bearer cached-token",
        }
        mock_cursor.fetchone.return_value = (json.dumps(cookie_data),)

        session = Session(self.username, self.password)
        session.load_cookies()

        # Verify cookie jar is populated
        self.assertEqual(session.cookies.get("fssessionid"), "cached-session-id")
        self.assertEqual(session.headers.get("Authorization"), "Bearer cached-token")

    @patch("getmyancestors.classes.session.GMASession.set_current", autospec=True)
    @patch("getmyancestors.classes.session.GMASession.load_cookies")
    @patch("sqlite3.connect")
    @patch("requests.Session.get")
    @patch("requests.Session.post")
    def test_login_reuse_valid_session(
        self, mock_post, mock_get, mock_connect, mock_load, mock_set_current
    ):
        # 1. Setup load_cookies to return True (session exists)
        mock_load.return_value = True

        # 2. Setup set_current to simulate success (sets fid)
        # Using autospec=True allows the mock to receive 'self' as the first argument
        def side_effect_set_current(self, auto_login=True):
            self.fid = "USER-123"
            self.cookies.set("fssessionid", "valid-id")

        mock_set_current.side_effect = side_effect_set_current

        # 3. Initialize session
        session = Session(self.username, self.password)

        # 4. Verify that the complex login flow was skipped (no POST requests made)
        self.assertEqual(mock_post.call_count, 0)
        self.assertEqual(session.fid, "USER-123")
        self.assertTrue(session.logged)

    @patch("builtins.input", return_value="mock_code")
    @patch("getmyancestors.classes.session.GMASession.manual_login")
    @patch("getmyancestors.classes.session.GMASession.set_current")
    @patch("getmyancestors.classes.session.GMASession.load_cookies")
    @patch("sqlite3.connect")
    @patch("requests.Session.get")
    @patch("requests.Session.post")
    def test_login_fallback_on_invalid_session(
        self,
        mock_post,
        mock_get,
        mock_connect,
        mock_load,
        mock_set_current,
        mock_manual,
        mock_input,
    ):
        # 1. Setup load_cookies to return True (session exists)
        mock_load.return_value = True

        # 2. Setup set_current to simulate failure (doesn't set fid)
        mock_set_current.return_value = None

        # 3. Setup mock_get to throw exception to break the headless flow
        # This exception is caught in login(), which then calls manual_login()
        mock_get.side_effect = Exception("Headless login failed")

        # 4. Initialize session - this triggers login() -> manual_login()
        # manual_login is mocked, so it should not prompt.
        Session(self.username, self.password)

        # 5. Verify that set_current was called with auto_login=False (reuse attempt)
        mock_set_current.assert_any_call(auto_login=False)

        # 6. Verify that manual_login was called (fallback triggered)
        self.assertTrue(mock_manual.called, "Fallback to manual_login should occur")


if __name__ == "__main__":
    unittest.main()

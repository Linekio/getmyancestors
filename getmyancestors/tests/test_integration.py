import os
import sys
import unittest
from unittest.mock import MagicMock, PropertyMock, patch

# Adjust path to allow imports from root of the repository
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from getmyancestors import getmyanc as getmyancestors


class TestFullIntegration(unittest.TestCase):
    @patch("webbrowser.open")
    @patch("getmyancestors.classes.session.GMASession.login", autospec=True)
    @patch(
        "getmyancestors.classes.session.GMASession.logged", new_callable=PropertyMock
    )
    @patch("requests.Session.get")
    @patch("requests.Session.post")
    def test_main_execution(
        self,
        mock_post,
        mock_get,
        mock_logged,
        mock_login,
        mock_browser,
    ):
        """
        Integration test for the main execution flow.
        Bypasses login logic and mocks network responses with static data.
        """

        # Setup mocks
        mock_logged.return_value = True

        # Define a fake login that calls set_current to populate session data
        def fake_login(self):
            # Calling self.set_current() will trigger self.get_url() -> self.get()
            self.set_current()

        mock_login.side_effect = fake_login
        mock_logged.return_value = True

        # Setup generic response for any GET request
        # users/current -> sets lang='en'
        generic_json = {
            "users": [
                {
                    "personId": "TEST-123",
                    "preferredLanguage": "en",
                    "displayName": "Integrator",
                }
            ],
            "persons": [
                {
                    "id": "TEST-123",
                    "living": True,
                    "names": [
                        {
                            "preferred": True,
                            "type": "http://gedcomx.org/BirthName",
                            "nameForms": [
                                {
                                    "fullText": "Test Person",
                                    "parts": [
                                        {
                                            "type": "http://gedcomx.org/Given",
                                            "value": "Test",
                                        },
                                        {
                                            "type": "http://gedcomx.org/Surname",
                                            "value": "Person",
                                        },
                                    ],
                                }
                            ],
                            "attribution": {"changeMessage": "Automated update"},
                        }
                    ],
                    "notes": [],  # Added notes list for get_notes()
                    "facts": [],
                    "display": {
                        "name": "Test Person",
                        "gender": "Male",
                        "lifespan": "1900-2000",
                    },
                }
            ],
            "childAndParentsRelationships": [],
            "parentAndChildRelationships": [],
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = generic_json
        mock_response.headers = {}

        # When Session.get is called, it returns our mock response
        def side_effect_get(url, *args, **kwargs):
            print(f"DEBUG: Mock GET called for {url}")
            return mock_response

        mock_get.side_effect = side_effect_get
        mock_post.return_value = mock_response

        # Output file path in .tmp directory
        output_file = os.path.abspath(".tmp/test_output.ged")
        settings_file = os.path.abspath(".tmp/test_output.settings")

        # Create the .tmp directory if it doesn't exist
        tmp_dir = os.path.dirname(output_file)
        os.makedirs(tmp_dir, exist_ok=True)

        # Prepare arguments mimicking CLI usage
        test_args = [
            "getmyancestors",
            "-u",
            "testuser",
            "-p",
            "testpass",
            "--no-cache",
            "--outfile",
            output_file,
        ]

        with patch.object(sys, "argv", test_args):
            try:
                getmyancestors.main()
            except SystemExit as e:
                # If it exits with 0 or None, it's a success
                if e.code not in [None, 0]:
                    print(f"SystemExit: {e.code}")
                    self.fail(f"main() exited with code {e.code}")

        # Basic assertions
        self.assertTrue(mock_login.called, "Login should have been called")
        self.assertTrue(mock_get.called, "Should have attempted network calls")

        self.assertTrue(
            os.path.exists(output_file),
            f"Output file should have been created at {output_file}",
        )

        # Cleanup
        if os.path.exists(output_file):
            os.remove(output_file)
        if os.path.exists(settings_file):
            os.remove(settings_file)
        # Also clean up the .tmp directory if it's empty
        if os.path.exists(tmp_dir) and not os.listdir(tmp_dir):
            os.rmdir(tmp_dir)


if __name__ == "__main__":
    unittest.main(verbosity=2)

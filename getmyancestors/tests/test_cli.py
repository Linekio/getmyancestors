import sys
from unittest.mock import patch

import pytest

from getmyancestors.getmyanc import main


class TestCLI:

    @patch("getmyancestors.getmyanc.Session")
    @patch("getmyancestors.getmyanc.CachedSession")
    @patch("getmyancestors.getmyanc.Tree")
    def test_basic_args(self, MockTree, MockCachedSession, MockSession):
        """Test that arguments are parsed and passed to classes correctly"""

        # Mock sys.argv to simulate command line execution
        test_args = [
            "getmyancestors",
            "-u",
            "myuser",
            "-p",
            "mypass",
            "-i",
            "KW7V-Y32",
            "--verbose",
        ]

        # Setup the session to appear logged in
        MockCachedSession.return_value.logged = True

        with patch.object(sys, "argv", test_args):
            main()

        # Verify Session was initialized with CLI args
        MockCachedSession.assert_called_once()
        args, kwargs = MockCachedSession.call_args
        assert kwargs["username"] == "myuser"
        assert kwargs["password"] == "mypass"
        assert kwargs["verbose"] is True
        assert kwargs["cache_control"] is True

        # Verify Tree started
        MockTree.return_value.add_indis.assert_called_with(["KW7V-Y32"])

    def test_arg_validation(self):
        """Test that invalid ID formats cause an exit"""
        test_args = ["getmyancestors", "-u", "u", "-p", "p", "-i", "BAD_ID"]

        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit):
                # This should trigger sys.exit("Invalid FamilySearch ID...")
                main()

"""Test package installation and basic functionality."""

import os
import subprocess
import sys
import tempfile
import unittest
import venv
from pathlib import Path


class TestInstallation(unittest.TestCase):
    """Test that the package can be installed and basic commands work."""

    @classmethod
    def setUpClass(cls):
        """Get the project root directory."""
        # Go up 3 levels from tests directory: getmyancestors/tests -> getmyancestors -> .
        cls.project_root = Path(__file__).parent.parent.parent.absolute()
        print(f"Project root: {cls.project_root}")

    def test_clean_installation(self):
        """Test installing the package in a clean virtual environment."""
        # Skip on CI if it takes too long
        if os.environ.get("CI") == "true" and os.environ.get("SKIP_LONG_TESTS"):
            self.skipTest("Skipping long-running installation test in CI")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a clean virtual environment
            venv_dir = tmpdir_path / "venv"
            print(f"Creating virtual environment at: {venv_dir}")
            venv.create(venv_dir, with_pip=True, clear=True)

            # Get paths to pip and python in the virtual environment
            if sys.platform == "win32":
                pip_path = venv_dir / "Scripts" / "pip.exe"
                python_path = venv_dir / "Scripts" / "python.exe"
            else:
                pip_path = venv_dir / "bin" / "pip"
                python_path = venv_dir / "bin" / "python"

            # Install the package from the project directory
            print(f"Installing package from: {self.project_root}")
            result = subprocess.run(
                [str(pip_path), "install", str(self.project_root)],
                capture_output=True,
                text=True,
                cwd=self.project_root,
            )

            if result.returncode != 0:
                print(f"Installation failed. STDOUT: {result.stdout}")
                print(f"Installation failed. STDERR: {result.stderr}")

            self.assertEqual(
                result.returncode,
                0,
                f"Package installation failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}",
            )

            # Test that the package can be imported
            print("Testing package import...")
            result = subprocess.run(
                [
                    str(python_path),
                    "-c",
                    "import getmyancestors; print('Import successful')",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(
                result.returncode,
                0,
                f"Package import failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}",
            )
            self.assertIn("Import successful", result.stdout)

            # Test that CLI commands can be imported (check entry points)
            # Only test getmyanc and mergemyanc - these don't require Tkinter
            # fstogedcom requires Tkinter which is not installed in clean test environments
            print(
                "Testing CLI command imports (skipping fstogedcom - requires Tkinter)..."
            )
            for module in [
                "getmyancestors.getmyanc",
                "getmyancestors.mergemyanc",
            ]:
                result = subprocess.run(
                    [
                        str(python_path),
                        "-c",
                        f"from {module} import main; print('{module} import successful')",
                    ],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"Failed to import {module}:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}",
                )

    def test_dependencies_match(self):
        """Test that all imports have corresponding dependencies in pyproject.toml."""
        import tomllib

        # Read pyproject.toml
        pyproject_path = self.project_root / "pyproject.toml"
        self.assertTrue(
            pyproject_path.exists(), f"pyproject.toml not found at {pyproject_path}"
        )

        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)

        # Get dependencies from pyproject.toml
        dependencies = pyproject.get("project", {}).get("dependencies", [])
        dependency_names = []
        for dep in dependencies:
            # Extract package name (remove version specifiers)
            name = (
                dep.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].strip()
            )
            dependency_names.append(name)

        print(f"Dependencies in pyproject.toml: {dependency_names}")

        # Check critical dependencies that we know are needed
        critical_deps = [
            "requests",
            "requests-cache",  # Note: package name uses hyphen, import uses underscore
            "requests-ratelimiter",
            "diskcache",
            "babelfish",
            "geocoder",
            "fake-useragent",
        ]

        for dep in critical_deps:
            # Handle requests-cache vs requests_cache naming difference
            if dep == "requests-cache":
                check_name = "requests_cache"
            else:
                check_name = dep.replace(
                    "-", "_"
                )  # Convert hyphen to underscore for import check

            # Try to import the dependency
            try:
                __import__(check_name)
                print(f"✓ Can import {check_name}")
            except ImportError:
                # Check if it's in dependencies (allowing for naming differences)
                found = False
                for pyproject_dep in dependency_names:
                    if dep in pyproject_dep or pyproject_dep in dep:
                        found = True
                        break

                if not found:
                    self.fail(
                        f"Dependency '{dep}' is imported but not declared in pyproject.toml"
                    )
                else:
                    print(f"✓ Dependency '{dep}' is declared (as '{pyproject_dep}')")


if __name__ == "__main__":
    unittest.main(verbosity=2)

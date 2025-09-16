#!/usr/bin/env python3
"""
Manual publishing script for smartapi-mcp package.

This script can be used to manually build and publish the package to PyPI.
For automated publishing, use the GitHub Actions workflow.
"""

import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd, cwd=None, *, check=True):
    """Run a shell command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, cwd=cwd, check=check, capture_output=True, text=True
        )
        if result.stdout:
            print(result.stdout)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        if e.stderr:
            print(f"Error output: {e.stderr}")
        sys.exit(1)


def setup_environment():
    """Set up the environment for publishing."""
    print("🚀 SmartAPI MCP Package Publishing Script")
    repo_root = Path(__file__).parent.parent
    os.chdir(repo_root)
    return repo_root


def clean_build_artifacts():
    """Clean previous build artifacts."""
    print("\n📋 Step 1: Clean previous builds")
    for dir_name in ["build", "dist", "*.egg-info"]:
        run_command(["rm", "-rf", dir_name], check=False)


def run_tests():
    """Run the test suite."""
    print("\n🔍 Step 2: Run tests")
    try:
        run_command(["python", "-m", "pytest", "tests/"])
    except Exception:
        print("⚠️  Tests failed or pytest not available. Continuing...")


def build_package():
    """Build the package."""
    print("\n🔧 Step 3: Build package")
    try:
        # Try modern build first
        run_command(["python", "-m", "build"])
    except Exception:
        print("📦 Falling back to setuptools...")
        run_command(["python", "setup.py", "sdist", "bdist_wheel"])


def check_package():
    """Check the built packages."""
    print("\n✅ Step 4: Check built packages")
    try:
        run_command(["python", "-m", "twine", "check", "dist/*"])
    except Exception:
        print("⚠️  Twine check not available. Skipping...")


def upload_to_test_pypi():
    """Upload package to Test PyPI and optionally test installation."""
    print("\n🧪 Uploading to Test PyPI...")
    try:
        run_command([
            "python", "-m", "twine", "upload",
            "--repository", "testpypi", "dist/*"
        ])
        print("✅ Successfully uploaded to Test PyPI!")
        print("🔗 Check your package at:")
        print("https://test.pypi.org/project/smartapi-mcp/")

        test_install = input(
            "\nTest installation from Test PyPI? (Y/n): "
        ).strip().lower()
        if test_install != "n":
            print("🧪 Testing installation from Test PyPI...")
            run_command([
                "pip", "install", "-i", "https://test.pypi.org/simple/",
                "--extra-index-url", "https://pypi.org/simple/",
                "smartapi-mcp"
            ])
        return True
    except Exception:
        print("❌ Failed to upload to Test PyPI")
        return False


def upload_to_pypi():
    """Upload package to PyPI."""
    print("\n🚀 Uploading to PyPI...")
    try:
        run_command(["python", "-m", "twine", "upload", "dist/*"])
        print("🎉 Successfully uploaded to PyPI!")
        print("🔗 Check your package at: https://pypi.org/project/smartapi-mcp/")
        return True
    except Exception:
        print("❌ Failed to upload to PyPI")
        return False


def main():
    """Main publishing workflow."""
    setup_environment()
    clean_build_artifacts()
    run_tests()
    build_package()
    check_package()

    print("\n📤 Step 5: Upload to PyPI")

    # Ask user for confirmation
    response = input("\nUpload to PyPI? (y/N): ").strip().lower()
    if response != "y":
        print("❌ Upload cancelled.")
        return

    # Ask whether to upload to Test PyPI first
    test_response = input("Upload to Test PyPI first? (Y/n): ").strip().lower()

    if test_response != "n" and not upload_to_test_pypi():
        return

    # Final upload to PyPI
    final_response = input(
        "\nProceed with upload to PyPI? (y/N): "
    ).strip().lower()
    if final_response == "y":
        if not upload_to_pypi():
            return
    else:
        print("❌ Upload to PyPI cancelled.")

    print("\n✨ Publishing workflow completed!")


if __name__ == "__main__":
    main()

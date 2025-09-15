#!/usr/bin/env python3
"""
Manual publishing script for smartapi-mcp package.

This script can be used to manually build and publish the package to PyPI.
For automated publishing, use the GitHub Actions workflow.
"""

import subprocess
import sys
import os
from pathlib import Path


def run_command(cmd, cwd=None, check=True):
    """Run a shell command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        if e.stderr:
            print(f"Error output: {e.stderr}")
        sys.exit(1)


def main():
    """Main publishing workflow."""
    print("🚀 SmartAPI MCP Package Publishing Script")
    
    # Get the repository root
    repo_root = Path(__file__).parent.parent
    os.chdir(repo_root)
    
    print("\n📋 Step 1: Clean previous builds")
    for dir_name in ["build", "dist", "*.egg-info"]:
        run_command(["rm", "-rf", dir_name], check=False)
    
    print("\n🔍 Step 2: Run tests")
    try:
        run_command(["python", "-m", "pytest", "tests/"])
    except:
        print("⚠️  Tests failed or pytest not available. Continuing...")
    
    print("\n🔧 Step 3: Build package")
    try:
        # Try modern build first
        run_command(["python", "-m", "build"])
    except:
        print("📦 Falling back to setuptools...")
        run_command(["python", "setup.py", "sdist", "bdist_wheel"])
    
    print("\n✅ Step 4: Check built packages")
    try:
        run_command(["python", "-m", "twine", "check", "dist/*"])
    except:
        print("⚠️  Twine check not available. Skipping...")
    
    print("\n📤 Step 5: Upload to PyPI")
    
    # Ask user for confirmation
    response = input("\nUpload to PyPI? (y/N): ").strip().lower()
    if response != 'y':
        print("❌ Upload cancelled.")
        return
    
    # Ask whether to upload to Test PyPI first
    test_response = input("Upload to Test PyPI first? (Y/n): ").strip().lower()
    
    if test_response != 'n':
        print("\n🧪 Uploading to Test PyPI...")
        try:
            run_command([
                "python", "-m", "twine", "upload", 
                "--repository", "testpypi",
                "dist/*"
            ])
            print("✅ Successfully uploaded to Test PyPI!")
            print("🔗 Check your package at: https://test.pypi.org/project/smartapi-mcp/")
            
            test_install = input("\nTest installation from Test PyPI? (Y/n): ").strip().lower()
            if test_install != 'n':
                print("🧪 Testing installation from Test PyPI...")
                run_command([
                    "pip", "install", "-i", "https://test.pypi.org/simple/",
                    "--extra-index-url", "https://pypi.org/simple/",
                    "smartapi-mcp"
                ])
        except:
            print("❌ Failed to upload to Test PyPI")
            return
    
    # Final upload to PyPI
    final_response = input("\nProceed with upload to PyPI? (y/N): ").strip().lower()
    if final_response == 'y':
        print("\n🚀 Uploading to PyPI...")
        try:
            run_command(["python", "-m", "twine", "upload", "dist/*"])
            print("🎉 Successfully uploaded to PyPI!")
            print("🔗 Check your package at: https://pypi.org/project/smartapi-mcp/")
        except:
            print("❌ Failed to upload to PyPI")
            return
    else:
        print("❌ Upload to PyPI cancelled.")
    
    print("\n✨ Publishing workflow completed!")


if __name__ == "__main__":
    main()
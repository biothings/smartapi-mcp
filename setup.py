"""
Legacy setup.py for backwards compatibility.
All configuration is now in pyproject.toml.
"""

from setuptools import setup

# Read the contents of your README file
from pathlib import Path
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
    name="smartapi-mcp",
    long_description=long_description,
    long_description_content_type="text/markdown",
)
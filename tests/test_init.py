"""
Tests for smartapi_mcp.__init__ module

Tests the package initialization and import error handling.
"""

import smartapi_mcp


def test_successful_import():
    """Test that normal imports work correctly."""
    # Re-import the module to test normal behavior

    # Check that all expected functions are available
    assert hasattr(smartapi_mcp, "get_smartapi_ids")
    assert hasattr(smartapi_mcp, "load_api_spec")
    assert hasattr(smartapi_mcp, "get_base_server_url")
    assert hasattr(smartapi_mcp, "__version__")

    # Check __all__ contains expected items
    expected_items = ["get_smartapi_ids", "load_api_spec", "get_base_server_url"]
    for item in expected_items:
        assert item in smartapi_mcp.__all__


def test_version_available():
    """Test that version information is always available."""

    # Version should always be available regardless of import errors
    assert hasattr(smartapi_mcp, "__version__")
    assert isinstance(smartapi_mcp.__version__, str)
    assert len(smartapi_mcp.__version__) > 0


def test_package_metadata():
    """Test package metadata is properly set."""

    # Check package metadata
    assert hasattr(smartapi_mcp, "__author__")
    assert hasattr(smartapi_mcp, "__email__")
    assert smartapi_mcp.__author__ == "BioThings Team"
    assert smartapi_mcp.__email__ == "help@biothings.io"


def test_module_docstring():
    """Test that module has proper docstring."""

    assert smartapi_mcp.__doc__ is not None
    assert len(smartapi_mcp.__doc__) > 0
    assert "SmartAPI MCP Server" in smartapi_mcp.__doc__

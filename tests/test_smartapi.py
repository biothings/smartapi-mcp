"""
Tests for smartapi-mcp.smartapi module
"""

from unittest.mock import patch

import pytest

from smartapi_mcp import get_base_server_url, get_smartapi_ids, load_api_spec

test_api_id = "59dce17363dce279d389100834e43648"  # MyGene.info


def test_package_imports():
    """Test that smartapi helper function imports work correctly."""
    assert get_base_server_url is not None
    assert get_smartapi_ids is not None


@pytest.mark.asyncio
async def test_get_smartapi_ids():
    """Test get_smartapi_ids helper function."""
    id_list = await get_smartapi_ids(q=test_api_id)
    assert len(id_list) == 1
    assert id_list[0] == test_api_id

    id_list = await get_smartapi_ids(q="tags.name:biothings")
    assert len(id_list) >= 30


def test_get_api_spec():
    api_spec = load_api_spec(test_api_id)
    info = api_spec["info"]
    assert "title" in info
    assert "version" in info
    assert "description" in info
    assert info["title"] == "MyGene.info API"


def test_get_base_server_url():
    """Test server info method."""
    api_spec = load_api_spec(test_api_id)
    base_url = get_base_server_url(api_spec)
    assert base_url == "https://mygene.info/v3"


def test_get_base_server_url_single_server():
    """Test get_base_server_url with single server."""
    api_spec = {
        "info": {"title": "Test API"},
        "servers": [{"url": "https://api.example.com"}],
    }
    base_url = get_base_server_url(api_spec)
    assert base_url == "https://api.example.com"


def test_get_base_server_url_multiple_servers_with_production():
    """Test get_base_server_url with multiple servers and production server."""
    api_spec = {
        "info": {"title": "Test API"},
        "servers": [
            {"url": "https://dev.api.example.com", "description": "Development server"},
            {
                "url": "https://api.example.com",
                "description": "Production server on https",
            },
            {"url": "https://staging.api.example.com", "description": "Staging server"},
        ],
    }
    base_url = get_base_server_url(api_spec)
    assert base_url == "https://api.example.com"


def test_get_base_server_url_multiple_servers_with_production_keyword():
    """Test get_base_server_url with multiple servers and Production keyword."""
    api_spec = {
        "info": {"title": "Test API"},
        "servers": [
            {"url": "https://dev.api.example.com", "description": "Development server"},
            {"url": "https://api.example.com", "description": "Production environment"},
            {"url": "https://staging.api.example.com", "description": "Staging server"},
        ],
    }
    base_url = get_base_server_url(api_spec)
    assert base_url == "https://api.example.com"


def test_get_base_server_url_multiple_servers_with_ci_transltr():
    """Test get_base_server_url with multiple servers and ci.transltr.io server."""
    api_spec = {
        "info": {"title": "Test API"},
        "servers": [
            {"url": "https://dev.api.example.com", "description": "Development server"},
            {
                "url": "https://api.ci.transltr.io/test",
                "description": "CI Translator server",
            },
            {"url": "https://staging.api.example.com", "description": "Staging server"},
        ],
    }
    base_url = get_base_server_url(api_spec)
    assert base_url == "https://api.ci.transltr.io/test"


def test_get_base_server_url_no_suitable_server():
    """Test get_base_server_url raises ValueError when no suitable server found."""
    api_spec = {
        "info": {"title": "Test API"},
        "servers": [
            {"url": "https://dev.api.example.com", "description": "Development server"},
            {"url": "https://staging.api.example.com", "description": "Staging server"},
        ],
    }
    with pytest.raises(ValueError, match="Cannot determine server URL") as exc_info:
        get_base_server_url(api_spec)

    assert "Cannot determine server URL for API: test_api" in str(exc_info.value)


def test_get_base_server_url_server_without_description():
    """Test get_base_server_url with servers that have no description."""
    api_spec = {
        "info": {"title": "Test API"},
        "servers": [
            {"url": "https://dev.api.example.com"},
            {
                "url": "https://api.example.com",
                "description": "Production server on https",
            },
        ],
    }
    base_url = get_base_server_url(api_spec)
    assert base_url == "https://api.example.com"


@patch("smartapi_mcp.smartapi.load_openapi_spec")
@patch("smartapi_mcp.smartapi.validate_openapi_spec")
@patch("smartapi_mcp.smartapi.logger")
def test_load_api_spec_validation_warning(mock_logger, mock_validate, mock_load):
    """Test load_api_spec logs warning when validation fails."""
    # Setup mocks
    mock_spec = {"info": {"title": "Test API"}}
    mock_load.return_value = mock_spec
    mock_validate.return_value = False  # Validation fails

    # Call function
    result = load_api_spec("test_id")

    # Verify result and warning
    assert result == mock_spec
    mock_logger.warning.assert_called_once_with(
        "OpenAPI specification validation failed, but continuing anyway"
    )


@patch("smartapi_mcp.smartapi.load_openapi_spec")
@patch("smartapi_mcp.smartapi.validate_openapi_spec")
@patch("smartapi_mcp.smartapi.logger")
def test_load_api_spec_validation_success(mock_logger, mock_validate, mock_load):
    """Test load_api_spec when validation succeeds."""
    # Setup mocks
    mock_spec = {"info": {"title": "Test API"}}
    mock_load.return_value = mock_spec
    mock_validate.return_value = True  # Validation succeeds

    # Call function
    result = load_api_spec("test_id")

    # Verify result and no warning
    assert result == mock_spec
    mock_logger.warning.assert_not_called()

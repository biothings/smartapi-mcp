"""
Tests for smartapi-mcp.smartapi module
"""

from unittest.mock import patch

import pytest

from smartapi_mcp.smartapi import (
    PREDEFINED_API_SETS,
    get_base_server_url,
    get_predefined_api_set,
    get_smartapi_ids,
    load_api_spec,
)

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


def test_get_predefined_api_set_biothings_core():
    """Test get_predefined_api_set with biothings_core set."""
    result = get_predefined_api_set("biothings_core")

    assert "smartapi_ids" in result
    assert isinstance(result["smartapi_ids"], list)
    assert len(result["smartapi_ids"]) == 5
    # Verify the core APIs are included
    expected_ids = [
        "59dce17363dce279d389100834e43648",  # MyGene.info
        "09c8782d9f4027712e65b95424adba79",  # MyVariant.info
        "8f08d1446e0bb9c2b323713ce83e2bd3",  # MyChem.info
        "671b45c0301c8624abbd26ae78449ca2",  # MyDisease.info
        "85139f4dccfcefa3ac3042372066916d",  # MyGeneSet.info
    ]
    for expected_id in expected_ids:
        assert expected_id in result["smartapi_ids"]


def test_get_predefined_api_set_biothings_test():
    """Test get_predefined_api_set with biothings_test set."""

    result = get_predefined_api_set("biothings_test")

    assert "smartapi_ids" in result
    assert isinstance(result["smartapi_ids"], list)
    assert len(result["smartapi_ids"]) == 6
    # Verify the test APIs are included (core + SemmedDB)
    expected_ids = [
        "59dce17363dce279d389100834e43648",  # MyGene.info
        "09c8782d9f4027712e65b95424adba79",  # MyVariant.info
        "8f08d1446e0bb9c2b323713ce83e2bd3",  # MyChem.info
        "671b45c0301c8624abbd26ae78449ca2",  # MyDisease.info
        "85139f4dccfcefa3ac3042372066916d",  # MyGeneSet.info
        "1d288b3a3caf75d541ffaae3aab386c8",  # SemmedDB
    ]
    for expected_id in expected_ids:
        assert expected_id in result["smartapi_ids"]


def test_get_predefined_api_set_biothings_all():
    """Test get_predefined_api_set with biothings_all set."""

    result = get_predefined_api_set("biothings_all")

    assert "smartapi_q" in result
    assert "smartapi_exclude_ids" in result
    assert isinstance(result["smartapi_q"], str)
    assert isinstance(result["smartapi_exclude_ids"], list)

    # Verify the query string
    expected_query = (
        "_status.uptime_status:pass AND tags.name=biothings AND NOT tags.name=trapi"
    )
    assert result["smartapi_q"] == expected_query

    # Verify exclusion list
    expected_exclusions = [
        "1c9be9e56f93f54192dcac203f21c357",  # BioThings mabs API
        "5a4c41bf2076b469a0e9cfcf2f2b8f29",  # Translator Annotation Service
        "cc857d5b7c8b7609b5bbb38ff990bfff",  # GO Biological Process API
        "f339b28426e7bf72028f60feefcd7465",  # GO Cellular Component API
        "34bad236d77bea0a0ee6c6cba5be54a6",  # GO Molecular Function API
    ]
    assert len(result["smartapi_exclude_ids"]) == 5
    for expected_id in expected_exclusions:
        assert expected_id in result["smartapi_exclude_ids"]


def test_get_predefined_api_set_unknown_set():
    """Test get_predefined_api_set raises ValueError for unknown set."""
    with pytest.raises(ValueError, match="Unknown API set: unknown_set"):
        get_predefined_api_set("unknown_set")


def test_get_predefined_api_set_empty_string():
    """Test get_predefined_api_set raises ValueError for empty string."""
    with pytest.raises(ValueError, match="Unknown API set: "):
        get_predefined_api_set("")


def test_predefined_api_sets_constant():
    """Test that PREDEFINED_API_SETS constant contains expected values."""
    expected_sets = ["biothings_core", "biothings_test", "biothings_all"]
    assert isinstance(PREDEFINED_API_SETS, list)
    assert len(PREDEFINED_API_SETS) == 3
    for expected_set in expected_sets:
        assert expected_set in PREDEFINED_API_SETS

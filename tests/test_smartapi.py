"""
Tests for smartapi-mcp.smartapi module
"""

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

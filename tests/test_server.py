"""
Tests for smartapi-mcp.smartapi module
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import FastMCP

from smartapi_mcp import get_mcp_server, get_merged_mcp_server, merge_mcp_servers

test_api_id_1 = "59dce17363dce279d389100834e43648"  # MyGene.info
test_api_id_2 = "8f08d1446e0bb9c2b323713ce83e2bd3"  # MyChem.info


@pytest.mark.asyncio
async def test_get_mcp_server():
    """Test get_mcp_server can create a MCP server based on a SmartAPI id."""
    server = await get_mcp_server(test_api_id_1)
    assert isinstance(server, FastMCP)
    tools = await server.get_tools()
    assert len(tools) >= 4
    assert server.name == "MyGene.info API"


@pytest.mark.asyncio
async def test_merge_mcp_servers():
    """Test merge_mcp_servers helper function."""
    list_of_servers = [
        await get_mcp_server(sid) for sid in [test_api_id_1, test_api_id_2]
    ]
    merged_server = await merge_mcp_servers(list_of_servers)
    assert isinstance(merged_server, FastMCP)
    assert merged_server.name == "merged_mcp"
    tools = await merged_server.get_tools()
    assert len(tools) >= 8


@pytest.mark.asyncio
async def test_get_merged_mcp_server():
    """Test merge_mcp_servers helper function."""
    merged_server = await get_merged_mcp_server(
        smartapi_ids=[test_api_id_1, test_api_id_2]
    )
    assert isinstance(merged_server, FastMCP)
    assert merged_server.name == "smartapi_mcp"
    tools = await merged_server.get_tools()
    assert len(tools) >= 8

    merged_server = await get_merged_mcp_server(
        smartapi_ids=[test_api_id_1, test_api_id_2],
        smartapi_exclude_ids=[test_api_id_1, test_api_id_2],
    )
    assert isinstance(merged_server, FastMCP)
    tools = await merged_server.get_tools()
    assert len(tools) == 0

    merged_server = await get_merged_mcp_server(smartapi_q=f"_id: {test_api_id_1}")
    assert isinstance(merged_server, FastMCP)
    tools = await merged_server.get_tools()
    assert len(tools) >= 4
    assert len(tools) <= 8


@pytest.mark.asyncio
async def test_merge_mcp_servers_no_accessible_tools():
    """Test merge_mcp_servers raises AttributeError when server has no accessible
    tools."""
    # Create a mock server that will trigger the AttributeError path
    mock_server = MagicMock()
    mock_server.name = "Mock Server"
    # Make get_tools return empty dict to simulate server without accessible tools
    mock_server.get_tools = AsyncMock(return_value={})

    with pytest.raises(AttributeError) as exc_info:
        await merge_mcp_servers([mock_server])

    assert "Server" in str(exc_info.value)
    assert "does not have accessible tools" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_merged_mcp_server_failure():
    """Test failure of get_merged_mcp_server helper function."""
    with pytest.raises(ValueError):
        await get_merged_mcp_server(smartapi_q="_id:unknown_id")

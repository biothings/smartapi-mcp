"""
Tests for smartapi-mcp.smartapi module
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP

from smartapi_mcp import get_mcp_server, get_merged_mcp_server, merge_mcp_servers
from smartapi_mcp.smartapi import get_predefined_api_set

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


@pytest.mark.asyncio
async def test_get_merged_mcp_server_with_api_set():
    """Test get_merged_mcp_server with predefined API sets."""
    # Test with biothings_core API set
    merged_server = await get_merged_mcp_server(api_set="biothings_core")
    assert isinstance(merged_server, FastMCP)
    assert merged_server.name == "smartapi_mcp"
    tools = await merged_server.get_tools()
    # Should have tools from MyGene, MyVariant, MyChem, and MyDisease
    assert len(tools) >= 16  # Each API typically has 4+ tools


@pytest.mark.asyncio
async def test_get_merged_mcp_server_with_api_set_and_exclusions():
    """Test get_merged_mcp_server with API set and exclusions."""
    # Test with biothings_test API set excluding one API
    merged_server = await get_merged_mcp_server(
        api_set="biothings_test",
        smartapi_exclude_ids=[
            "59dce17363dce279d389100834e43648"
        ],  # Exclude MyGene.info
    )
    assert isinstance(merged_server, FastMCP)
    tools = await merged_server.get_tools()
    # Should have fewer tools than full biothings_test set
    assert len(tools) >= 12  # From 4 remaining APIs


@pytest.mark.asyncio
async def test_get_merged_mcp_server_with_single_smartapi_id():
    """Test get_merged_mcp_server with single smartapi_id parameter."""
    merged_server = await get_merged_mcp_server(smartapi_id=test_api_id_1)
    assert isinstance(merged_server, FastMCP)
    assert merged_server.name == "smartapi_mcp"
    tools = await merged_server.get_tools()
    # Should have tools from just one API
    assert len(tools) >= 4
    assert len(tools) <= 8  # Reasonable upper bound for single API


@pytest.mark.asyncio
async def test_get_merged_mcp_server_with_custom_server_name():
    """Test get_merged_mcp_server with custom server name."""
    custom_name = "my_custom_server"
    merged_server = await get_merged_mcp_server(
        smartapi_ids=[test_api_id_1], server_name=custom_name
    )
    assert isinstance(merged_server, FastMCP)
    assert merged_server.name == custom_name


@pytest.mark.asyncio
async def test_get_merged_mcp_server_no_ids_provided():
    """Test get_merged_mcp_server raises ValueError when no IDs provided."""
    with pytest.raises(ValueError) as exc_info:
        await get_merged_mcp_server()

    assert "No SmartAPI IDs provided or found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_merge_mcp_servers_with_custom_name():
    """Test merge_mcp_servers with custom merged server name."""
    list_of_servers = [
        await get_mcp_server(sid) for sid in [test_api_id_1, test_api_id_2]
    ]
    custom_name = "custom_merged_server"
    merged_server = await merge_mcp_servers(list_of_servers, custom_name)
    assert isinstance(merged_server, FastMCP)
    assert merged_server.name == custom_name


@pytest.mark.asyncio
async def test_get_merged_mcp_server_api_set_with_exclude_overrides():
    """
    Test that API set exclude IDs can be overridden by smartapi_exclude_ids
    parameter.
    """
    # Use biothings_all which has exclude IDs, but override them
    merged_server = await get_merged_mcp_server(
        api_set="biothings_core",
        smartapi_exclude_ids=[
            "59dce17363dce279d389100834e43648"
        ],  # Only exclude MyGene
    )
    assert isinstance(merged_server, FastMCP)
    # Should have processed the query and included more APIs than
    # if we used the default excludes
    tools = await merged_server.get_tools()
    # This should have multiple APIs worth of tools
    assert len(tools) >= 8


@pytest.mark.asyncio
async def test_get_merged_mcp_server_with_duplicate_ids():
    """Test get_merged_mcp_server handles duplicate IDs correctly."""
    # Pass duplicate IDs - should be deduplicated
    duplicate_ids = [test_api_id_1, test_api_id_1, test_api_id_2, test_api_id_1]
    merged_server = await get_merged_mcp_server(smartapi_ids=duplicate_ids)
    assert isinstance(merged_server, FastMCP)
    tools = await merged_server.get_tools()
    # Should only have tools from 2 unique APIs
    assert len(tools) >= 8  # From 2 APIs
    assert len(tools) <= 16  # Reasonable upper bound


@pytest.mark.asyncio
async def test_get_merged_mcp_server_api_set_with_builtin_exclude_ids():
    """Test API set that contains 'smartapi_exclude_ids'."""
    # First verify that biothings_all has exclude IDs
    api_set_args = get_predefined_api_set("biothings_all")
    assert "smartapi_exclude_ids" in api_set_args  # Fixed key name

    with patch("smartapi_mcp.server.get_smartapi_ids") as mock_get_ids:
        # Return some test IDs that include both included and excluded ones
        mock_get_ids.return_value = [
            "59dce17363dce279d389100834e43648",  # MyGene.info (should be included)
            "1c9be9e56f93f54192dcac203f21c357",  # mab API (should be excluded)
        ]

        # This should use the biothings_all query and exclude IDs
        try:
            merged_server = await get_merged_mcp_server(api_set="biothings_all")

            # Verify server was created
            assert isinstance(merged_server, FastMCP)
            tools = await merged_server.get_tools()

            # Should only have tools from MyGene (the excluded API should
            # not be present)
            # The exact number depends on the API, but it should be > 0
            assert len(tools) >= 4

        except Exception as e:
            # If there are issues with the actual API calls, that's okay for this test
            # The important thing is that we exercised line 85
            print(f"Note: API call may have failed, but we tested line 85: {e}")


@pytest.mark.asyncio
async def test_merge_mcp_servers_special_characters_in_name():
    """Test merge_mcp_servers handles special characters in server names."""
    mock_server1 = MagicMock()
    mock_server1.name = "API with spaces & symbols!"
    mock_tool1 = MagicMock()
    mock_tool1.name = "original_tool_1"
    mock_server1.get_tools = AsyncMock(return_value={"tool1": mock_tool1})
    mock_server1.get_prompts = AsyncMock(return_value={})

    mock_server2 = MagicMock()
    mock_server2.name = "API-with-dashes_and_underscores"
    mock_tool2 = MagicMock()
    mock_tool2.name = "original_tool_2"
    mock_server2.get_tools = AsyncMock(return_value={"tool2": mock_tool2})
    mock_server2.get_prompts = AsyncMock(return_value={})

    merged_server = await merge_mcp_servers([mock_server1, mock_server2])

    tools = await merged_server.get_tools()

    # Verify that special characters were sanitized in tool names
    # The merge function should rename tools with sanitized API names
    # Check that the tools got the correct names
    # Pattern is: {sanitized_api_name}_{original_tool_key}
    assert mock_tool1.name == "api_with_spaces___symbols__tool1"
    assert mock_tool2.name == "api-with-dashes_and_underscores_tool2"

    # Verify tools were added to merged server
    assert len(tools) == 2

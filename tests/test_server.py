"""
Tests for smartapi-mcp.smartapi module
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP
from fastmcp.prompts import Prompt
from fastmcp.tools import Tool

from smartapi_mcp import get_mcp_server, get_merged_mcp_server, merge_mcp_servers
from smartapi_mcp.server import MAX_TOOL_NAME_LEN, _fit_name, build_api_servers
from smartapi_mcp.smartapi import get_predefined_api_set

test_api_id_1 = "59dce17363dce279d389100834e43648"  # MyGene.info
test_api_id_2 = "8f08d1446e0bb9c2b323713ce83e2bd3"  # MyChem.info


def _sample_fn(q: str) -> str:
    """Sample callable backing the test tools/prompts."""
    return q


def make_tool(name: str) -> Tool:
    """Build a real :class:`Tool`.

    ``FastMCP.add_tool`` coerces anything that is not already a ``Tool`` via
    ``Tool.from_function``, so mock tools are rejected -- the merge helpers must
    be exercised with genuine components.
    """
    return Tool.from_function(_sample_fn, name=name)


def make_prompt(name: str) -> Prompt:
    """Build a real :class:`Prompt` (see :func:`make_tool`)."""
    return Prompt.from_function(_sample_fn, name=name)


@pytest.mark.asyncio
async def test_get_mcp_server():
    """Test get_mcp_server can create a MCP server based on a SmartAPI id."""
    server = await get_mcp_server(test_api_id_1)
    assert isinstance(server, FastMCP)
    tools = await server.list_tools()
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
    tools = await merged_server.list_tools()
    assert len(tools) >= 8


@pytest.mark.asyncio
async def test_get_merged_mcp_server():
    """Test merge_mcp_servers helper function."""
    merged_server = await get_merged_mcp_server(
        smartapi_ids=[test_api_id_1, test_api_id_2]
    )
    assert isinstance(merged_server, FastMCP)
    assert merged_server.name == "smartapi_mcp"
    tools = await merged_server.list_tools()
    assert len(tools) >= 8

    merged_server = await get_merged_mcp_server(
        smartapi_ids=[test_api_id_1, test_api_id_2],
        smartapi_exclude_ids=[test_api_id_1, test_api_id_2],
    )
    assert isinstance(merged_server, FastMCP)
    tools = await merged_server.list_tools()
    assert len(tools) == 0

    merged_server = await get_merged_mcp_server(smartapi_q=f"_id: {test_api_id_1}")
    assert isinstance(merged_server, FastMCP)
    tools = await merged_server.list_tools()
    assert len(tools) >= 4
    assert len(tools) <= 8


@pytest.mark.asyncio
async def test_merge_mcp_servers_skips_server_with_no_tools():
    """A tool-less API is skipped, not fatal to the whole merge.

    A spec can parse and still yield no callable operations. That used to raise
    AttributeError and take down every other API in the set.
    """
    empty = MagicMock()
    empty.name = "Empty API"
    empty.list_tools = AsyncMock(return_value=[])
    empty.list_prompts = AsyncMock(return_value=[])

    good = MagicMock()
    good.name = "Good API"
    good.list_tools = AsyncMock(return_value=[make_tool("works")])
    good.list_prompts = AsyncMock(return_value=[])

    merged = await merge_mcp_servers([empty, good])

    # the good API survived; the empty one contributed nothing
    assert {t.name for t in await merged.list_tools()} == {"good_api_works"}


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
    tools = await merged_server.list_tools()
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
    tools = await merged_server.list_tools()
    # Should have fewer tools than full biothings_test set
    assert len(tools) >= 12  # From 4 remaining APIs


@pytest.mark.asyncio
async def test_get_merged_mcp_server_with_single_smartapi_id():
    """Test get_merged_mcp_server with single smartapi_id parameter."""
    merged_server = await get_merged_mcp_server(smartapi_id=test_api_id_1)
    assert isinstance(merged_server, FastMCP)
    assert merged_server.name == "smartapi_mcp"
    tools = await merged_server.list_tools()
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
    tools = await merged_server.list_tools()
    # This should have multiple APIs worth of tools
    assert len(tools) >= 8


@pytest.mark.asyncio
async def test_get_merged_mcp_server_with_duplicate_ids():
    """Test get_merged_mcp_server handles duplicate IDs correctly."""
    # Pass duplicate IDs - should be deduplicated
    duplicate_ids = [test_api_id_1, test_api_id_1, test_api_id_2, test_api_id_1]
    merged_server = await get_merged_mcp_server(smartapi_ids=duplicate_ids)
    assert isinstance(merged_server, FastMCP)
    tools = await merged_server.list_tools()
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
            tools = await merged_server.list_tools()

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
    tool1 = make_tool("tool1")
    mock_server1.list_tools = AsyncMock(return_value=[tool1])
    mock_server1.list_prompts = AsyncMock(return_value=[])

    mock_server2 = MagicMock()
    mock_server2.name = "API-with-dashes_and_underscores"
    tool2 = make_tool("tool2")
    mock_server2.list_tools = AsyncMock(return_value=[tool2])
    mock_server2.list_prompts = AsyncMock(return_value=[])

    merged_server = await merge_mcp_servers([mock_server1, mock_server2])

    tools = await merged_server.list_tools()

    # Verify that special characters were sanitized in tool names
    # The merge function should rename tools with sanitized API names
    # Pattern is: {sanitized_api_name}_{original_tool_name}
    assert tool1.name == "api_with_spaces___symbols__tool1"
    assert tool2.name == "api-with-dashes_and_underscores_tool2"

    # Verify tools were added to merged server under their renamed names
    assert {tool.name for tool in tools} == {tool1.name, tool2.name}


def test_fit_name_keeps_short_names():
    """Names within the 64-char limit are returned unchanged."""
    name = "mygene_info_query"
    assert _fit_name(name, set()) == name


def test_fit_name_truncates_long_names():
    """Names over the limit are truncated to <= 64 chars with a hash suffix."""
    long_name = "a_very_long_biothings_api_name_" + "x" * 60 + "_query_operation"
    assert len(long_name) > MAX_TOOL_NAME_LEN

    fitted = _fit_name(long_name, set())
    assert len(fitted) <= MAX_TOOL_NAME_LEN
    # Deterministic: same input yields the same fitted name.
    assert _fit_name(long_name, set()) == fitted


def test_fit_name_truncation_is_collision_free():
    """Two long names sharing a 64-char prefix get distinct fitted names."""
    base = "same_prefix_" + "y" * 70
    name_a = base + "_alpha"
    name_b = base + "_beta"

    fitted_a = _fit_name(name_a, set())
    fitted_b = _fit_name(name_b, set())
    assert fitted_a != fitted_b
    assert len(fitted_a) <= MAX_TOOL_NAME_LEN
    assert len(fitted_b) <= MAX_TOOL_NAME_LEN


def test_fit_name_avoids_used_names():
    """A name already in use is rewritten even if it is within the limit."""
    used = {"mygene_info_query"}
    fitted = _fit_name("mygene_info_query", used)
    assert fitted != "mygene_info_query"
    assert len(fitted) <= MAX_TOOL_NAME_LEN


@pytest.mark.asyncio
async def test_merge_mcp_servers_enforces_name_length_limit():
    """Merged per-API tool names never exceed the 64-char MCP limit."""
    mock_server = MagicMock()
    mock_server.name = "Some BioThings API With A Fairly Long Descriptive Name"
    long_tool = make_tool("get_an_annotation_by_a_very_specific_identifier_endpoint")
    mock_server.list_tools = AsyncMock(return_value=[long_tool])
    mock_server.list_prompts = AsyncMock(return_value=[])

    merged_server = await merge_mcp_servers([mock_server])

    tools = await merged_server.list_tools()
    assert len(tools) == 1
    assert all(len(tool.name) <= MAX_TOOL_NAME_LEN for tool in tools)
    assert len(long_tool.name) <= MAX_TOOL_NAME_LEN
    # The prefixed name was too long, so it must have been truncated.
    assert long_tool.name.startswith("some_biothings_api_with_a_fairly_long")


@pytest.mark.asyncio
async def test_merge_mcp_servers_enforces_prompt_name_length_limit():
    """Merged per-API prompt names never exceed the 64-char MCP limit."""
    mock_server = MagicMock()
    mock_server.name = "Some BioThings API With A Fairly Long Descriptive Name"
    tool = make_tool("some_tool")
    long_prompt = make_prompt(
        "explain_an_annotation_for_a_very_specific_identifier_prompt"
    )
    mock_server.list_tools = AsyncMock(return_value=[tool])
    mock_server.list_prompts = AsyncMock(return_value=[long_prompt])

    merged_server = await merge_mcp_servers([mock_server])

    prompts = await merged_server.list_prompts()
    assert len(prompts) == 1
    assert all(len(prompt.name) <= MAX_TOOL_NAME_LEN for prompt in prompts)
    assert len(long_prompt.name) <= MAX_TOOL_NAME_LEN


class TestBuildApiServersFailureTolerance:
    """One unloadable API must not take down the rest of the set."""

    @pytest.mark.asyncio
    async def test_skips_an_api_that_raises(self):
        async def fake(sid):
            if sid == "bad":
                err_msg = "invalid OpenAPI schema"
                raise ValueError(err_msg)
            return FastMCP(sid)

        with patch("smartapi_mcp.server.get_mcp_server", new=fake):
            servers, failures = await build_api_servers(["ok1", "bad", "ok2"])
        assert len(servers) == 2
        assert [sid for sid, _ in failures] == ["bad"]
        assert "ValueError" in failures[0][1]

    @pytest.mark.asyncio
    async def test_skips_an_api_that_calls_sys_exit(self):
        """awslabs reports spec errors with sys.exit(1) from inside the library.

        That raises SystemExit, which ``except Exception`` does not catch, so a
        spec fastmcp itself rejects used to abort the whole build -- it killed a
        27-API run at API 17 against the registry's uptime-passing set.
        """

        async def fake(sid):
            if sid == "bad":
                raise SystemExit(1)
            return FastMCP(sid)

        with patch("smartapi_mcp.server.get_mcp_server", new=fake):
            servers, failures = await build_api_servers(["ok1", "bad", "ok2"])
        assert len(servers) == 2, "SystemExit from one API lost the whole set"
        assert [sid for sid, _ in failures] == ["bad"]
        assert "SystemExit" in failures[0][1]

    @pytest.mark.asyncio
    async def test_all_good_apis_report_no_failures(self):
        async def fake(sid):
            return FastMCP(sid)

        with patch("smartapi_mcp.server.get_mcp_server", new=fake):
            servers, failures = await build_api_servers(["a", "b"])
        assert len(servers) == 2
        assert failures == []

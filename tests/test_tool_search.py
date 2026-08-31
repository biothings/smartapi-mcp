"""
Tests for the tool-search transform wiring (smartapi_mcp.server.apply_tool_search)

These build synthetic FastMCP servers rather than hitting the SmartAPI registry,
so they exercise the transform behaviour without network access.
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP
from fastmcp.tools import Tool

from smartapi_mcp.config import Config, load_config
from smartapi_mcp.server import (
    TOOL_SEARCH_MODES,
    apply_tool_search,
    build_server_for_set,
)

SYNTHETIC_TOOLS = {
    "mygene_query": "Search genes by symbol, name or other gene annotation fields.",
    "mygene_get_by_id": "Retrieve a single gene annotation object by Entrez id.",
    "myvariant_query": "Search variants by rsid, HGVS or other variant fields.",
    "myvariant_get_by_id": "Retrieve a single variant annotation object by HGVS id.",
    "mychem_metadata": "Return metadata about the chemical annotation dataset.",
}


def build_server(name: str = "test_server") -> FastMCP:
    """A server with a handful of realistically-named/described tools."""
    server = FastMCP(name)
    for tool_name, description in SYNTHETIC_TOOLS.items():

        def fn(q: str = "") -> str:
            return q

        server.add_tool(Tool.from_function(fn, name=tool_name, description=description))
    return server


async def listed_names(server: FastMCP) -> set[str]:
    return {tool.name for tool in await server.list_tools()}


@pytest.mark.asyncio
async def test_tool_search_off_leaves_catalog_alone():
    """mode='off' is a no-op: every tool stays listed."""
    server = build_server()
    returned = await apply_tool_search(server, "off")
    assert returned is server
    assert await listed_names(server) == set(SYNTHETIC_TOOLS)


@pytest.mark.parametrize("mode", ["bm25", "regex"])
@pytest.mark.asyncio
async def test_tool_search_collapses_catalog(mode):
    """Enabled modes replace the listing with the two synthetic tools."""
    server = build_server()
    await apply_tool_search(server, mode)
    assert await listed_names(server) == {"search_tools", "call_tool"}


@pytest.mark.asyncio
async def test_tool_search_pins_always_visible():
    """Names in always_visible stay listed next to the synthetic tools."""
    server = build_server()
    await apply_tool_search(
        server, "bm25", always_visible=["mygene_query", "mychem_metadata"]
    )
    assert await listed_names(server) == {
        "mygene_query",
        "mychem_metadata",
        "search_tools",
        "call_tool",
    }


@pytest.mark.asyncio
async def test_collapsed_tools_remain_callable():
    """A tool that is no longer listed is still reachable via call_tool."""
    server = build_server()
    await apply_tool_search(server, "bm25")

    result = await server.call_tool(
        "call_tool", {"name": "mygene_get_by_id", "arguments": {"q": "1017"}}
    )
    assert "1017" in result.content[0].text


@pytest.mark.asyncio
async def test_search_finds_relevant_tool():
    """BM25 ranks a plausible query onto the matching tool."""
    server = build_server()
    await apply_tool_search(server, "bm25")

    result = await server.call_tool("search_tools", {"query": "variant by HGVS id"})
    text = result.content[0].text
    assert "myvariant_get_by_id" in text
    # An unrelated tool should not crowd out the results.
    assert "mychem_metadata" not in text


@pytest.mark.asyncio
async def test_search_respects_max_results():
    """max_results caps how many tools a single search returns."""
    server = build_server()
    await apply_tool_search(server, "bm25", max_results=2)

    result = await server.call_tool("search_tools", {"query": "query annotation id"})
    # The markdown serializer emits one '### <name>' heading per hit.
    headings = [
        line for line in result.content[0].text.splitlines() if line.startswith("### ")
    ]
    assert len(headings) <= 2


@pytest.mark.asyncio
async def test_tool_search_rejects_unknown_mode():
    """An unknown mode fails loudly rather than silently doing nothing."""
    server = build_server()
    with pytest.raises(ValueError, match="Unknown tool search mode"):
        await apply_tool_search(server, "fuzzy")


@pytest.mark.asyncio
async def test_tool_search_skips_empty_server():
    """An empty catalog is left alone so 'no tools registered' checks still fire."""
    server = FastMCP("empty")
    await apply_tool_search(server, "bm25")
    assert await listed_names(server) == set()


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("off", set(SYNTHETIC_TOOLS)),
        ("bm25", {"search_tools", "call_tool"}),
    ],
)
@pytest.mark.asyncio
async def test_build_server_for_set_plumbs_tool_search(mode, expected):
    """build_server_for_set applies the transform on the per-API path.

    ``get_merged_mcp_server`` is patched out so this exercises the plumbing
    without touching the SmartAPI registry.
    """
    with patch(
        "smartapi_mcp.server.get_merged_mcp_server",
        new=AsyncMock(return_value=build_server()),
    ):
        server = await build_server_for_set(
            smartapi_ids=["fake-id"], facade="off", tool_search=mode
        )
    assert await listed_names(server) == expected


def test_tool_search_modes_contains_off_first():
    """'off' is the documented default and must remain a valid choice."""
    assert TOOL_SEARCH_MODES[0] == "off"
    assert set(TOOL_SEARCH_MODES) == {"off", "bm25", "regex"}


class TestToolSearchConfig:
    """tool_search reaches Config from defaults, env vars and CLI args."""

    def test_defaults_to_off(self):
        config = Config()
        assert config.tool_search == "off"
        assert config.tool_search_max_results == 5

    @patch("smartapi_mcp.config.logger")
    @patch("awslabs.openapi_mcp_server.api.config.load_config")
    def test_from_environment(self, mock_base_load_config, mock_logger):
        mock_base_load_config.return_value = MagicMock()
        env = {"SMARTAPI_TOOL_SEARCH": "BM25", "TOOL_SEARCH_MAX_RESULTS": "12"}
        with (
            patch.dict(os.environ, env, clear=False),
            patch("smartapi_mcp.config.fields", return_value=[]),
        ):
            config = load_config()
        # Env values are normalised to lower case, like SMARTAPI_FACADE.
        assert config.tool_search == "bm25"
        assert config.tool_search_max_results == 12

    @patch("smartapi_mcp.config.logger")
    @patch("awslabs.openapi_mcp_server.api.config.load_config")
    def test_args_override_environment(self, mock_base_load_config, mock_logger):
        mock_base_load_config.return_value = MagicMock()
        args = SimpleNamespace(tool_search="regex", tool_search_max_results=3)
        env = {"SMARTAPI_TOOL_SEARCH": "bm25", "TOOL_SEARCH_MAX_RESULTS": "12"}
        with (
            patch.dict(os.environ, env, clear=False),
            patch("smartapi_mcp.config.fields", return_value=[]),
        ):
            config = load_config(args)
        assert config.tool_search == "regex"
        assert config.tool_search_max_results == 3

    @patch("smartapi_mcp.config.logger")
    @patch("awslabs.openapi_mcp_server.api.config.load_config")
    def test_bad_max_results_falls_back_to_default(
        self, mock_base_load_config, mock_logger
    ):
        mock_base_load_config.return_value = MagicMock()
        with (
            patch.dict(os.environ, {"TOOL_SEARCH_MAX_RESULTS": "not-a-number"}),
            patch("smartapi_mcp.config.fields", return_value=[]),
        ):
            config = load_config()
        assert config.tool_search_max_results == 5

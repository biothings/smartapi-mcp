"""
SmartAPI MCP Server

Main MCP server implementation for SmartAPI integration.
"""

import re

from awslabs.openapi_mcp_server import logger
from awslabs.openapi_mcp_server.api.config import Config
from fastmcp import FastMCP

from .awslabs_server import create_mcp_server
from .smartapi import (
    get_base_server_url,
    get_predefined_api_set,
    get_smartapi_ids,
    load_api_spec,
)


async def get_mcp_server(smartapi_id: str) -> FastMCP:
    config = Config(
        api_spec_url=f"https://smart-api.info/api/metadata/{smartapi_id}",
    )
    openapi_spec = load_api_spec(smartapi_id)
    base_server_url = get_base_server_url(openapi_spec)
    config.api_base_url = base_server_url

    return await create_mcp_server(config)


async def merge_mcp_servers(
    list_of_servers: list[FastMCP], merged_name: str = "merged_mcp"
) -> FastMCP:
    """
    Merges a list of FastMCP instances into a single FastMCP instance by combining their
    tools, prefixing tool names with the server's name (API name) to avoid conflicts.

    Args:
        list_of_servers: List of FastMCP instances to merge.
        merged_name: Name for the merged FastMCP instance.

    Returns:
        A new FastMCP instance with renamed tools from all input servers.
    """
    merged_mcp = FastMCP(merged_name)

    for server in list_of_servers:
        api_name = re.sub(
            r"[^a-z0-9_-]", "_", getattr(server, "name", "unknown_api").lower()
        )
        tools = await server.get_tools()
        if tools:
            for original_name, tool in tools.items():
                # Rename the tool by prefixing with API name
                new_name = f"{api_name}_{original_name}"
                tool.name = new_name  # Modify the tool's name attribute

                # Add the renamed tool to the merged instance
                merged_mcp.add_tool(tool)
        else:
            err_msg = f"Server {server} does not have accessible tools."
            raise AttributeError(err_msg)

    return merged_mcp


async def get_merged_mcp_server(
    smartapi_q: str | None = None,
    smartapi_id: str | None = None,
    smartapi_ids: list[str] | None = None,
    smartapi_exclude_ids: list[str] | None = None,
    api_set: str | None = None,
    server_name: str = "smartapi_mcp",
) -> FastMCP:
    logger.debug(f"api_set: {api_set}")
    if api_set:
        api_set_args = get_predefined_api_set(api_set)
        if "smartapi_ids" in api_set_args:
            smartapi_ids = api_set_args["smartapi_ids"]
        if "smartapi_q" in api_set_args:
            smartapi_q = api_set_args["smartapi_q"]
        if "smartapi_exclude_ids" in api_set_args:
            smartapi_exclude_ids = api_set_args["smartapi_exclude_ids"]
        logger.debug(f"api_set_args: {api_set_args}")
    logger.debug(f"smartapi_ids: {smartapi_ids}")
    logger.debug(f"smartapi_q: {smartapi_q}")
    logger.debug(f"smartapi_exclude_ids: {smartapi_exclude_ids}")
    if smartapi_q:
        smartapi_ids = await get_smartapi_ids(smartapi_q)
    if smartapi_id:
        smartapi_ids = [smartapi_id]
    if smartapi_ids:
        smartapi_ids = list(set(smartapi_ids))
    if not smartapi_ids:
        err_msg = "No SmartAPI IDs provided or found with the given query."
        raise ValueError(err_msg)
    smartapi_exclude_ids = smartapi_exclude_ids or []
    list_of_servers = [
        await get_mcp_server(sid)
        for sid in smartapi_ids
        if sid not in smartapi_exclude_ids
    ]
    merged_server = await merge_mcp_servers(list_of_servers, server_name)
    logger.info(f"Merged {len(list_of_servers)} APIs into one MCP server.")
    return merged_server

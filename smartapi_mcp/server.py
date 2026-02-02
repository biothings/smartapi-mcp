"""
SmartAPI MCP Server

Main MCP server implementation for SmartAPI integration.
"""

import re

from awslabs.openapi_mcp_server import logger
from awslabs.openapi_mcp_server.api.config import Config
from awslabs.openapi_mcp_server.server import create_mcp_server_async
from fastmcp import FastMCP

# Import router functions
from .router import create_progressive_server, create_smart_router_server

# Import from smartapi module - avoiding circular imports
from .smartapi import (
    get_base_server_url,
    get_predefined_api_set,
    get_smartapi_ids,
    load_api_spec,
    smartapi_spec_url,
)


async def get_mcp_server(smartapi_id: str) -> FastMCP:
    config = Config(
        api_spec_url=smartapi_spec_url.format(smartapi_id=smartapi_id),
    )
    openapi_spec = load_api_spec(smartapi_id)
    base_server_url = get_base_server_url(openapi_spec)
    config.api_base_url = base_server_url

    return await create_mcp_server_async(config)


async def merge_mcp_servers(
    list_of_servers: list[FastMCP], merged_name: str = "merged_mcp"
) -> FastMCP:
    """
    Merges a list of FastMCP instances into
    a single FastMCP instance by combining their
    tools, prefixing tool names with the server's
    name (API name) to avoid conflicts.

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

        # Merge prompts
        prompts = await server.get_prompts()
        if prompts:
            for original_name, prompt in prompts.items():
                # Rename the prompt by prefixing with API name
                new_name = f"{api_name}_{original_name}"
                prompt.name = new_name  # Modify the prompt's name attribute
                # Add the renamed prompt to the merged instance
                merged_mcp.add_prompt(prompt)
            logger.debug(f"Merged {len(prompts)} prompts from {api_name}")

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


async def get_smart_mcp_server_with_routing(
    smartapi_q: str | None = None,
    smartapi_id: str | None = None,
    smartapi_ids: list[str] | None = None,
    smartapi_exclude_ids: list[str] | None = None,
    api_set: str | None = None,
    server_name: str = "smartapi_mcp",
    *,
    smart_routing: bool = False,
    max_context_tools: int = 50,
) -> FastMCP:
    """Smart MCP server with intelligent routing and progressive loading"""
    logger.debug(
        "Creating smart MCP server: routing=%s, max_tools=%s",
        smart_routing,
        max_context_tools,
    )

    # Resolve API IDs from various sources
    if api_set:
        api_set_args = get_predefined_api_set(api_set)
        if "smartapi_ids" in api_set_args:
            smartapi_ids = api_set_args["smartapi_ids"]
        if "smartapi_q" in api_set_args:
            smartapi_q = api_set_args["smartapi_q"]
        if "smartapi_exclude_ids" in api_set_args:
            smartapi_exclude_ids = api_set_args["smartapi_exclude_ids"]

    if smartapi_q:
        smartapi_ids = await get_smartapi_ids(smartapi_q)

    if smartapi_id:
        smartapi_ids = [smartapi_id]

    if not smartapi_ids:
        err_msg = "No SmartAPI IDs provided or found with the given query."
        raise ValueError(err_msg)

    smartapi_exclude_ids = smartapi_exclude_ids or []
    available_ids = [sid for sid in smartapi_ids if sid not in smartapi_exclude_ids]

    large_api_threshold = 50
    medium_api_threshold = 10

    # Use smart routing for large API sets
    if smart_routing and len(available_ids) >= large_api_threshold:
        logger.info("🔍 Using smart routing for large API set")
        return await create_smart_router_server(
            available_ids, server_name, max_context_tools
        )

    # Use progressive loading for medium sets
    if len(available_ids) >= medium_api_threshold:
        logger.info("📦 Using progressive loading for medium API set")
        return await create_progressive_server(
            available_ids, server_name, max_context_tools
        )

    # Default to full loading for small sets
    logger.info("🔧 Using full loading for small API set")
    return await get_merged_mcp_server(
        smartapi_q=smartapi_q,
        smartapi_ids=available_ids,
        smartapi_exclude_ids=smartapi_exclude_ids,
        api_set=api_set,
        server_name=server_name,
    )

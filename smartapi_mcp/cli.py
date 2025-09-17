"""
Command Line Interface for SmartAPI MCP Server

Provides CLI commands for running and managing the SmartAPI MCP server.
"""

import argparse
import asyncio
import sys
import traceback

from awslabs.openapi_mcp_server import logger
from awslabs.openapi_mcp_server.server import setup_signal_handlers

from .awslabs_server import get_all_counts
from .config import load_config
from .server import get_merged_mcp_server


def main():
    parser = argparse.ArgumentParser(
        description="Create MCP tools based on multiple registered SmartAPI APIs."
    )
    parser.add_argument(
        "--api_set",
        help=(
            "the set of predefined SmartAPI APIs to include, e.g. 'biothings_core' "
            "or 'biothings'."
        ),
    )
    parser.add_argument(
        "--smartapi_id",
        help="Pass a single SmartAPI (id) to create a MCP server.",
    )
    parser.add_argument(
        "--smartapi_ids",
        help="Pass a list of SmartAPIs (comma-separated ids) to create a MCP server.",
    )
    parser.add_argument(
        "--smartapi_q",
        help="Pass a query string for a list of SmartAPIs to create a MCP server.",
    )
    parser.add_argument(
        "--smartapi_exclude_ids",
        help=(
            "Exclude a list of SmartAPIs (comma-separated ids) to create a MCP server."
        ),
    )
    parser.add_argument(
        "--host",
        help="The host address for the MCP server in HTTP mode. Default is localhost.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="The http port for the MCP server in HTTP mode. Default is 8000.",
    )
    parser.add_argument(
        "--transport",
        help="The transport mode for the MCP server, either stdio (default) or http.",
    )
    parser.add_argument(
        "--server_name",
        help='The name of the MCP server, default is "smartapi_mcp".',
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set logging level",
    )

    args = parser.parse_args()

    # Set up logging with loguru at specified level
    logger.remove()
    logger.add(lambda msg: print(msg, end=""), level=args.log_level)
    logger.info(f"Starting server with logging level: {args.log_level}")

    # Load configuration
    logger.debug("Loading configuration from arguments and environment")
    config = load_config(args)
    logger.debug("Configuration loaded.")

    merged_server = asyncio.run(
        get_merged_mcp_server(
            smartapi_q=config.smartapi_q,
            smartapi_id=config.smartapi_id,
            smartapi_ids=config.smartapi_ids,
            smartapi_exclude_ids=config.smartapi_exclude_ids,
            api_set=config.smartapi_api_set,
            server_name=config.server_name,
        )
    )

    # Set up signal handlers
    setup_signal_handlers()

    try:
        prompt_count, tool_count, resource_count, resource_template_count = asyncio.run(
            get_all_counts(merged_server)
        )

        # Log all counts in a single statement
        logger.info(
            f"Server components: {prompt_count} prompts, {tool_count} tools, "
            f"{resource_count} resources, {resource_template_count} resource templates"
        )

        # Check if we have at least one tool or resource
        if tool_count == 0 and resource_count == 0:
            logger.warning(
                (
                    "No tools or resources were registered. This might "
                    "indicate an issue "
                    "with the API specification or authentication."
                ),
            )
    except Exception as e:
        logger.error(f"Error counting tools and resources: {e}")
        logger.error("Server shutting down due to error in tool/resource registration.")
        logger.error(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)

    if config.transport in ["http", "sse"]:
        # Run server with http transport only
        logger.info(f"Running server with {config.transport} transport")
        merged_server.run(
            transport=config.transport, host=config.host, port=config.port
        )
        return
    # Otherwise run server with stdio transport by default
    logger.info("Running server with stdio transport")
    merged_server.run()


if __name__ == "__main__":
    main()

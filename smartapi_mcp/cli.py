"""
Command Line Interface for SmartAPI MCP Server

Provides CLI commands for running and managing the SmartAPI MCP server.
"""

import argparse
import asyncio
import sys

from awslabs.openapi_mcp_server import logger
from awslabs.openapi_mcp_server.server import setup_signal_handlers

from .awslabs_server import get_all_counts
from .server import get_merged_mcp_server


def main():
    parser = argparse.ArgumentParser(
        description="Create MCP tools based on multiple registered SmartAPI APIs."
    )
    parser.add_argument(
        "--api_set",
        help="the set of predefined SmartAPI APIs to include, e.g. 'biothings_core' or 'biothings'.",
    )
    parser.add_argument(
        "--mode",
        help="The mode of MCP server, either stdio or http. Default is stdio.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="The http port for the MCP server in HTTP mode. Default is 8001.",
    )
    args = parser.parse_args()

    if args.api_set == "biothings_core":
        smartapi_ids = [
            "59dce17363dce279d389100834e43648",  # MyGene.info
            "09c8782d9f4027712e65b95424adba79",  # MyVariant.info
            "8f08d1446e0bb9c2b323713ce83e2bd3",  # MyChem.info
            "671b45c0301c8624abbd26ae78449ca2",  # MyDisease.info
            "1d288b3a3caf75d541ffaae3aab386c8",  # SemmedDB
        ]
        merged_server = asyncio.run(
            get_merged_mcp_server(smartapi_ids=smartapi_ids, server_name="smartapi_mcp")
        )
    else:
        # args.api_set == "biothings" this is the default
        smartapi_q = (
            "_status.uptime_status:pass AND tags.name=biothings AND NOT tags.name=trapi"
        )

        smartapi_ids_excluded = [
            "1c9be9e56f93f54192dcac203f21c357",  # BioThings mabs API
            "5a4c41bf2076b469a0e9cfcf2f2b8f29",  # Translator Annotation Service
            "cc857d5b7c8b7609b5bbb38ff990bfff",  # BioThings GO Biological Process API
            "f339b28426e7bf72028f60feefcd7465",  # BioThings GO Cellular Component API
            "34bad236d77bea0a0ee6c6cba5be54a6",  # BioThings GO Molecular Function API
        ]
        merged_server = asyncio.run(
            get_merged_mcp_server(
                smartapi_q=smartapi_q,
                server_name="smartapi_mcp",
                exclude_ids=smartapi_ids_excluded,
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
            f"Server components: {prompt_count} prompts, {tool_count} tools, {resource_count} resources, {resource_template_count} resource templates"
        )

        # Check if we have at least one tool or resource
        if tool_count == 0 and resource_count == 0:
            logger.warning(
                "No tools or resources were registered. This might indicate an issue with the API specification or authentication."
            )
    except Exception as e:
        logger.error(f"Error counting tools and resources: {e}")
        logger.error("Server shutting down due to error in tool/resource registration.")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)

    if args.mode == "http":
        # Run server with stdio transport only
        logger.info("Running server with HTTP transport")
        merged_server.run(transport="http", host="127.0.0.1", port=args.port)
        return
    # Otherwise run server with stdio transport by default
    logger.info("Running server with stdio transport")
    merged_server.run()


if __name__ == "__main__":
    main()

"""
Command Line Interface for SmartAPI MCP Server

Provides CLI commands for running and managing the SmartAPI MCP server.
"""

import argparse
import asyncio
import signal
import sys
import traceback

from fastmcp import FastMCP

from .config import load_config
from .log import get_format, logger
from .server import TOOL_SEARCH_MODES, build_server_for_set


async def get_all_counts(server: FastMCP) -> tuple[int, int, int, int]:
    """Return ``(prompts, tools, resources, resource_templates)`` for ``server``.

    Used only for the startup summary and the "nothing got registered" warning.
    """
    prompts = await server.list_prompts()
    tools = await server.list_tools()
    resources = await server.list_resources()
    resource_templates = await server.list_resource_templates()
    return len(prompts), len(tools), len(resources), len(resource_templates)


def main():
    parser = argparse.ArgumentParser(
        description="Create MCP tools based on multiple registered SmartAPI APIs."
    )
    parser.add_argument(
        "--api_set",
        help=(
            "A predefined set of SmartAPI APIs to include. One of: "
            "'biothings_core' (the 6 core BioThings APIs), 'biothings_test' "
            "(core + SemmedDB), or 'biothings_all' (all BioThings APIs). "
            "[env: SMARTAPI_API_SET]"
        ),
    )
    parser.add_argument(
        "--smartapi_id",
        help=("Pass a single SmartAPI (id) to create a MCP server. [env: SMARTAPI_ID]"),
    )
    parser.add_argument(
        "--smartapi_ids",
        help=(
            "Pass a list of SmartAPIs (comma-separated ids) to create a MCP "
            "server. [env: SMARTAPI_IDS]"
        ),
    )
    parser.add_argument(
        "--smartapi_q",
        help=(
            "A SmartAPI registry search query selecting which APIs to include, "
            "e.g. 'tags.name:biothings'. [env: SMARTAPI_Q]"
        ),
    )
    parser.add_argument(
        "--smartapi_exclude_ids",
        help=(
            "Exclude a list of SmartAPIs (comma-separated ids) to create a MCP "
            "server. [env: SMARTAPI_EXCLUDE_IDS]"
        ),
    )
    parser.add_argument(
        "--host",
        help=(
            "The host address for the MCP server in HTTP mode. Default is "
            "localhost. [env: SERVER_HOST]"
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=(
            "The http port for the MCP server in HTTP mode. Default is 8000. "
            "[env: SERVER_PORT]"
        ),
    )
    parser.add_argument(
        "--transport",
        help=(
            "The transport mode for the MCP server, either stdio (default) or "
            "http. [env: SERVER_TRANSPORT]"
        ),
    )
    parser.add_argument(
        "--server_name",
        help=(
            'The name of the MCP server, default is "smartapi_mcp". [env: SERVER_NAME]'
        ),
    )
    parser.add_argument(
        "--facade",
        choices=["auto", "on", "off"],
        default=None,
        help=(
            "How to expose large BioThings sets. The facade collapses BioThings "
            "APIs into ~5 generic tools (the target API is a parameter); any "
            "non-BioThings APIs in the set are added as per-API tools (hybrid). "
            "'auto' (default): use the facade once there are enough BioThings "
            "APIs (see --facade-threshold). 'on': always use it for BioThings "
            "APIs. 'off': always emit faithful per-API tools for every API. "
            "[env: SMARTAPI_FACADE]"
        ),
    )
    parser.add_argument(
        "--facade-threshold",
        type=int,
        default=None,
        help=(
            "Number of BioThings APIs in the set at which 'auto' switches to the "
            "facade (default: 10). [env: FACADE_THRESHOLD]"
        ),
    )
    parser.add_argument(
        "--facade-strict",
        action="store_true",
        help=(
            "Inspect BioThings specs and serve any API that has non-standard "
            "endpoints (e.g. SemmedDB's /query/ngd) with faithful per-API tools "
            "instead of the facade. Slower startup (downloads specs upfront). "
            "[env: FACADE_STRICT]"
        ),
    )
    parser.add_argument(
        "--tool-search",
        choices=list(TOOL_SEARCH_MODES),
        default=None,
        help=(
            "How to expose the tool listing. Serving many APIs produces hundreds "
            "of tools, which crowds out a client's context. When search is on, "
            "clients see 'search_tools' and 'call_tool' (plus any facade tools, "
            "which stay listed) and discover the rest on demand; every tool "
            "remains callable via 'call_tool'. 'auto' (default) turns search on "
            "once the server reaches --tool-search-threshold tools. 'bm25' and "
            "'regex' force it on regardless of size; 'off' always lists "
            "everything. Prefer 'bm25' over 'regex': regex needs a real pattern "
            "and returns nothing if given a natural-language query. CLI "
            "overrides the environment variable, which overrides the default. "
            "[env: SMARTAPI_TOOL_SEARCH]"
        ),
    )
    parser.add_argument(
        "--tool-search-threshold",
        type=int,
        default=None,
        help=(
            "Tool count at which --tool-search 'auto' turns search on "
            "(default: 15). A listed tool costs ~300-1000 tokens of client "
            "context, so 15 is roughly a 5-15k-token ceiling on the listing. "
            "[env: TOOL_SEARCH_THRESHOLD]"
        ),
    )
    parser.add_argument(
        "--tool-search-max-results",
        type=int,
        default=None,
        help=(
            "Maximum number of tools returned per 'search_tools' call "
            "(default: 10). Only used when tool search is active. "
            "[env: TOOL_SEARCH_MAX_RESULTS]"
        ),
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
    logger.add(sys.stderr, format=get_format(), level=args.log_level)
    logger.info(f"Starting server with logging level: {args.log_level}")

    # Load configuration
    logger.debug("Loading configuration from arguments and environment")
    config = load_config(args)

    logger.debug("Configuration loaded.")

    try:
        merged_server = asyncio.run(
            build_server_for_set(
                smartapi_q=config.smartapi_q,
                smartapi_id=config.smartapi_id,
                smartapi_ids=config.smartapi_ids,
                smartapi_exclude_ids=config.smartapi_exclude_ids,
                api_set=config.smartapi_api_set,
                server_name=config.server_name,
                facade=config.facade,
                facade_threshold=config.facade_threshold,
                facade_strict=config.facade_strict,
                tool_search=config.tool_search,
                tool_search_max_results=config.tool_search_max_results,
                tool_search_threshold=config.tool_search_threshold,
            )
        )
    except ValueError as e:
        logger.error(f"Cannot start server: {e}")
        logger.error(
            "Specify which APIs to serve with one of: --api_set, --smartapi_id, "
            "--smartapi_ids, or --smartapi_q (see --help)."
        )
        sys.exit(1)

    # Set up signal handlers (local implementation avoids sys.exit in handler)
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


def setup_signal_handlers() -> None:
    """
    Set up signal handlers for graceful shutdown without sys.exit.

    Calling sys.exit from inside a signal handler raises SystemExit on whatever
    frame happens to be executing, which can interrupt the event loop mid-await;
    restoring the default handler and re-raising lets the runtime unwind.
    """
    handled = {"done": False}

    def _handler(sig, frame):  # noqa: ARG001
        if handled["done"]:
            return
        handled["done"] = True

        logger.debug("Received signal %s, shutting down gracefully...", sig)

        if sig == signal.SIGINT:
            logger.info("Process Interrupted, Shutting down gracefully...")

        logger.info("Shutdown complete.")

        # Restore default handler and re-raise signal to let runtime unwind cleanly
        signal.signal(sig, signal.SIG_DFL)
        signal.raise_signal(sig)

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


if __name__ == "__main__":
    main()

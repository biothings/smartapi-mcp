"""
Configuration for the SmartAPI MCP server.

``Config`` used to subclass ``awslabs.openapi_mcp_server.api.config.Config`` and
inherit its ~40 fields, of which this package read five (``api_spec_url``,
``api_base_url``, ``host``, ``port``, ``transport``); the other thirty-five
covered authentication schemes, Cognito, tag filtering and multi-spec
composition that SmartAPI's public APIs never used. It is now a standalone
dataclass carrying only what is actually read.

Precedence is CLI argument > environment variable > default. That relies on
argparse passing ``None`` for unset flags: ``load_config`` assigns from ``args``
whenever the attribute is truthy, so a non-``None`` argparse default would
silently overwrite the environment on every run. ``cli.py`` sets those defaults
to ``None`` and ``tests/test_tool_search.py`` guards it.
"""

import os
from dataclasses import dataclass
from typing import Any

from .log import logger


@dataclass
class Config:
    """Everything the server needs to decide what to serve and how."""

    # Per-API values, filled in while building each API's server rather than by
    # the operator. Kept on Config because the build path threads them through.
    api_base_url: str = ""
    api_spec_url: str = ""

    # MCP server transport
    host: str = "127.0.0.1"
    port: int = 8000
    transport: str = "stdio"  # stdio or http
    server_name: str = "smartapi_mcp"

    # Which SmartAPI APIs to serve
    smartapi_id: str = ""
    smartapi_ids: list[str] | None = None
    smartapi_exclude_ids: list[str] | None = None
    smartapi_q: str = ""
    smartapi_api_set: str = ""

    # BioThings generic facade
    facade: str = "auto"
    facade_threshold: int = 10
    facade_strict: bool = False

    # Tool-search transform
    tool_search: str = "auto"
    tool_search_max_results: int = 10
    tool_search_threshold: int = 15


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_config(args: Any = None) -> Config:
    """Build a :class:`Config` from environment variables and CLI arguments."""
    config = Config()

    env_vars = {
        "SMARTAPI_ID": (lambda v: setattr(config, "smartapi_id", v)),
        "SMARTAPI_IDS": (lambda v: setattr(config, "smartapi_ids", v.split(","))),
        "SMARTAPI_EXCLUDE_IDS": (
            lambda v: setattr(config, "smartapi_exclude_ids", v.split(","))
        ),
        "SMARTAPI_Q": (lambda v: setattr(config, "smartapi_q", v)),
        "SMARTAPI_API_SET": (lambda v: setattr(config, "smartapi_api_set", v)),
        "SMARTAPI_FACADE": (lambda v: setattr(config, "facade", v.strip().lower())),
        "FACADE_THRESHOLD": (
            lambda v: setattr(config, "facade_threshold", _parse_int(v, 10))
        ),
        "FACADE_STRICT": (lambda v: setattr(config, "facade_strict", _parse_bool(v))),
        "SMARTAPI_TOOL_SEARCH": (
            lambda v: setattr(config, "tool_search", v.strip().lower())
        ),
        "TOOL_SEARCH_MAX_RESULTS": (
            lambda v: setattr(config, "tool_search_max_results", _parse_int(v, 10))
        ),
        "TOOL_SEARCH_THRESHOLD": (
            lambda v: setattr(config, "tool_search_threshold", _parse_int(v, 15))
        ),
        "SERVER_NAME": (lambda v: setattr(config, "server_name", v)),
        "SERVER_HOST": (lambda v: setattr(config, "host", v)),
        "SERVER_PORT": (lambda v: setattr(config, "port", _parse_int(v, 8000))),
        "SERVER_TRANSPORT": (lambda v: setattr(config, "transport", v)),
        "API_SPEC_URL": (lambda v: setattr(config, "api_spec_url", v)),
        "API_BASE_URL": (lambda v: setattr(config, "api_base_url", v)),
    }

    env_loaded = {}
    for key, setter in env_vars.items():
        if key in os.environ:
            env_value = os.environ[key]
            setter(env_value)
            env_loaded[key] = env_value

    if env_loaded:
        logger.debug(
            f"Loaded {len(env_loaded)} environment variables: "
            f"{', '.join(env_loaded.keys())}"
        )

    if args:
        if getattr(args, "smartapi_id", None):
            logger.debug(f"Setting SmartAPI id from arguments: {args.smartapi_id}")
            config.smartapi_id = args.smartapi_id
        if getattr(args, "smartapi_ids", None):
            logger.debug(f"Setting SmartAPI ids from arguments: {args.smartapi_ids}")
            # smartapi_ids from arguments is comma-separated
            config.smartapi_ids = (
                args.smartapi_ids.split(",")
                if isinstance(args.smartapi_ids, str)
                else args.smartapi_ids
            )
        if getattr(args, "smartapi_exclude_ids", None):
            logger.debug(
                f"Setting excluded SmartAPI ids from arguments: "
                f"{args.smartapi_exclude_ids}"
            )
            # smartapi_exclude_ids from arguments is comma-separated
            config.smartapi_exclude_ids = (
                args.smartapi_exclude_ids.split(",")
                if isinstance(args.smartapi_exclude_ids, str)
                else args.smartapi_exclude_ids
            )
        if getattr(args, "smartapi_q", None):
            logger.debug(f"Setting SmartAPI query from arguments: {args.smartapi_q}")
            config.smartapi_q = args.smartapi_q
        if getattr(args, "api_set", None):
            logger.debug(
                f"Setting predefined SmartAPI API set from arguments: {args.api_set}"
            )
            config.smartapi_api_set = args.api_set
        if getattr(args, "server_name", None):
            logger.debug(f"Setting MCP Server name from arguments: {args.server_name}")
            config.server_name = args.server_name
        if getattr(args, "facade", None):
            config.facade = str(args.facade).strip().lower()
        if getattr(args, "facade_threshold", None):
            config.facade_threshold = int(args.facade_threshold)
        if getattr(args, "facade_strict", False):
            config.facade_strict = True
        if getattr(args, "tool_search", None):
            config.tool_search = str(args.tool_search).strip().lower()
        if getattr(args, "tool_search_max_results", None):
            config.tool_search_max_results = int(args.tool_search_max_results)
        if getattr(args, "tool_search_threshold", None):
            config.tool_search_threshold = int(args.tool_search_threshold)
        if getattr(args, "transport", None):
            logger.debug(
                f"Setting MCP Server transport mode from arguments: {args.transport}"
            )
            config.transport = args.transport
        if getattr(args, "host", None):
            logger.debug(f"Setting MCP Server host from arguments: {args.host}")
            config.host = args.host
        if getattr(args, "port", None):
            logger.debug(f"Setting MCP Server port from arguments: {args.port}")
            config.port = int(args.port)

    logger.info("SmartAPI Configuration loaded")
    return config

"""
Configuration for the SmartAPI MCP server.

``Config`` used to subclass ``awslabs.openapi_mcp_server.api.config.Config`` and
inherit its ~40 fields, of which this package read five (``api_spec_url``,
``api_base_url``, ``host``, ``port``, ``transport``); the other thirty-five
covered authentication schemes, Cognito, tag filtering and multi-spec
composition that SmartAPI's public APIs never used. It is now a standalone
dataclass carrying only what is actually read. (``api_spec_url`` and
``api_base_url`` stopped being read when awslabs was dropped and were removed
in 0.6.0; ``spec_urls`` is the replacement for the former.)

Precedence is CLI argument > environment variable > default. That relies on
argparse passing ``None`` for unset flags: ``load_config`` assigns from ``args``
whenever the attribute is truthy, so a non-``None`` argparse default would
silently overwrite the environment on every run. ``cli.py`` sets those defaults
to ``None`` and ``tests/test_tool_search.py`` guards it.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Config:
    """Everything the server needs to decide what to serve and how."""

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
    # Spec URLs or local files to serve alongside (or instead of) the above
    spec_urls: list[str] | None = None

    # Logging
    log_level: str = "INFO"

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


def _split_list(values: list[str]) -> list[str]:
    """Flatten comma-separated ``values`` into a deduped list, dropping blanks."""
    items = (item.strip() for value in values for item in value.split(","))
    return list(dict.fromkeys(item for item in items if item))


LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

# Checked in order; the first one set wins. LOG_LEVEL is the generic name many
# deployment environments already set, SMARTAPI_LOG_LEVEL the specific one.
LOG_LEVEL_ENV_VARS = ("SMARTAPI_LOG_LEVEL", "LOG_LEVEL")


def resolve_log_level(cli_value: str | None = None, *, warn: bool = False) -> str:
    """Return the log level from ``--log-level``, the environment, or ``INFO``.

    Precedence is ``cli_value`` > ``SMARTAPI_LOG_LEVEL`` > ``LOG_LEVEL``. An
    unrecognised environment value falls back to ``INFO`` rather than failing,
    since ``LOG_LEVEL`` may be set for some other program with its own
    vocabulary (``trace``, ``verbose``, a number). ``warn`` logs that fallback;
    the CLI resolves the level once silently to configure logging, then again
    through :func:`load_config` with ``warn=True`` so the warning is visible.
    """
    if cli_value:
        return cli_value.upper()
    for name in LOG_LEVEL_ENV_VARS:
        value = os.environ.get(name, "").strip()
        if not value:
            continue
        if value.upper() in LOG_LEVELS:
            return value.upper()
        if warn:
            logger.warning(
                f"Ignoring {name}={value!r}: not one of {', '.join(LOG_LEVELS)}. "
                "Using INFO."
            )
        return "INFO"
    return "INFO"


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
        "SMARTAPI_SPEC_URLS": (
            lambda v: setattr(config, "spec_urls", _split_list([v]))
        ),
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
    }

    env_loaded = {}
    for key, setter in env_vars.items():
        if key in os.environ:
            env_value = os.environ[key]
            setter(env_value)
            env_loaded[key] = env_value

    config.log_level = resolve_log_level(
        getattr(args, "log_level", None) if args else None, warn=True
    )
    for name in LOG_LEVEL_ENV_VARS:
        if name in os.environ:
            env_loaded[name] = os.environ[name]

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
        if getattr(args, "spec_url", None):
            # A repeatable flag, each value optionally comma-separated.
            values = args.spec_url
            config.spec_urls = _split_list(
                [values] if isinstance(values, str) else list(values)
            )
            logger.debug(f"Setting spec URLs from arguments: {config.spec_urls}")
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

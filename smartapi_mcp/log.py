"""
Logging setup for smartapi-mcp.

Provides the ``logger`` and ``get_format()`` that every other module imports.
These were previously re-exported from ``awslabs.openapi_mcp_server``, which
configured a loguru sink as an import side effect; this module keeps that
arrangement (same format, same stderr sink, same default level) so log output
is unchanged, without depending on the awslabs package for it.

Importing this module removes loguru's default handler and installs ours. That
is a side effect, which is normally worth avoiding -- but a library that logs to
stderr on import is what the rest of the package was written against, and
``cli.py`` deliberately reconfigures the sink afterwards to honour
``--log-level``.
"""

import sys

from loguru import logger

__all__ = ["get_format", "logger"]


def get_format() -> str:
    """Return the loguru format string used for all smartapi-mcp output.

    Includes the logger name, function and line number, which is what makes
    warnings about a specific API traceable back to the code that emitted them.
    """
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )


# Replace loguru's default handler with our own so the format is consistent and
# the level is explicit. ``cli.py`` calls remove()/add() again to apply
# --log-level; doing it here keeps library use (importing smartapi_mcp without
# the CLI) from logging in loguru's default format.
logger.remove()
logger.add(sys.stderr, format=get_format(), level="INFO")

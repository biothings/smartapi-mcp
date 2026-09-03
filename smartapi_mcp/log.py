"""
Logging setup for smartapi-mcp.

This package logs through the standard library. Each module holds its own
``logging.getLogger(__name__)``, so records carry the real dotted module name
and can be filtered per module; nothing is configured at import time beyond a
:class:`~logging.NullHandler`, which is the documented way for a library to stay
out of an application's way.

That last point is why this is not loguru any more. loguru has a single global
logger, so installing our own sink meant calling ``logger.remove()`` at import
time -- which removed *the host application's* handlers too. Importing
``smartapi_mcp`` would silently redirect an app's logging into our stderr sink
and drop whatever it had configured. Since this package used only
``debug``/``info``/``warning``/``error`` and none of loguru's distinguishing
features, the standard library covers the whole requirement, and it also unifies
us with fastmcp, mcp and httpx2, which register ~48 stdlib loggers of their own
-- so ``--log-level`` now reaches their diagnostics as well as ours.

Applications embedding this package should just configure logging themselves
(``logging.basicConfig(...)``); records will propagate normally. The CLI calls
:func:`configure_logging` to install the coloured stderr handler.
"""

import logging
import sys
from typing import TextIO

__all__ = ["LOGGER_NAME", "configure_logging", "get_format"]

# Root of this package's logger namespace. Per-module loggers
# (``smartapi_mcp.server``, ``smartapi_mcp.openapi``, ...) are children of it,
# so one handler and one level here govern all of them.
LOGGER_NAME = "smartapi_mcp"

# Matches the format used through 0.5.0, so log output is unchanged.
LOG_FORMAT = (
    "%(asctime)s.%(msecs)03d | %(levelname)s | "
    "%(name)s:%(funcName)s:%(lineno)d - %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ANSI colours, chosen to match the previous loguru scheme.
_LEVEL_COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[1m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[41m",
}
_GREEN = "\033[32m"
_CYAN = "\033[36m"
_RESET = "\033[0m"


def get_format() -> str:
    """Return the ``logging`` format string used for all smartapi-mcp output."""
    return LOG_FORMAT


class ColorFormatter(logging.Formatter):
    """Format records like the previous loguru sink, optionally with colour.

    Colour is applied to the timestamp, the level and the call site. It is
    switched off when the stream is not a terminal, so redirected output and
    captured logs stay free of escape sequences.
    """

    def __init__(self, *, color: bool = True) -> None:
        super().__init__(LOG_FORMAT, datefmt=DATE_FORMAT)
        self.color = color

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        if not self.color:
            return text
        # Re-split the rendered line rather than building it twice, so the
        # plain and coloured forms cannot drift apart.
        try:
            stamp, level, rest = text.split(" | ", 2)
            site, sep, message = rest.partition(" - ")
        except ValueError:  # pragma: no cover - message contained no separator
            return text
        if not sep:  # pragma: no cover - defensive
            return text
        level_color = _LEVEL_COLORS.get(record.levelname, "")
        return (
            f"{_GREEN}{stamp}{_RESET} | {level_color}{level}{_RESET} | "
            f"{_CYAN}{site}{_RESET} - {level_color}{message}{_RESET}"
        )


def configure_logging(
    level: str = "INFO",
    stream: TextIO | None = None,
    *,
    color: bool | None = None,
) -> logging.Logger:
    """Install a stderr handler on this package's logger and return it.

    Intended for the CLI and for programmatic users who want our formatting.
    Importing the package does *not* call this: a library that configures
    logging on import takes a decision that belongs to the application.

    Replaces any handler this function previously added, so calling it twice
    (as the CLI does, once per ``--log-level``) does not duplicate output.
    ``color`` defaults to whether ``stream`` is a terminal.
    """
    logger = logging.getLogger(LOGGER_NAME)
    stream = stream if stream is not None else sys.stderr
    if color is None:
        color = bool(getattr(stream, "isatty", lambda: False)())

    for handler in [h for h in logger.handlers if getattr(h, "_smartapi_mcp", False)]:
        logger.removeHandler(handler)

    handler = logging.StreamHandler(stream)
    handler.setFormatter(ColorFormatter(color=color))
    handler.setLevel(level.upper())
    handler._smartapi_mcp = True  # type: ignore[attr-defined]  # our own marker
    logger.addHandler(handler)
    logger.setLevel(level.upper())
    # Our handler already writes to stderr; propagating would duplicate the
    # record onto the root logger's handlers if the application configured one.
    logger.propagate = False
    return logger


# The one thing that *is* safe to do at import time: a NullHandler on the
# package logger, so records do not trigger logging's "no handler" warning when
# an application has not configured anything.
logging.getLogger(LOGGER_NAME).addHandler(logging.NullHandler())

"""
Tests for smartapi_mcp.log

The behaviour these pin is *library hygiene*: importing this package must not
disturb an application's logging. That is what the move off loguru bought --
loguru has one global logger, so installing our sink meant calling
``logger.remove()`` at import time, which removed the host's handlers too.
"""

import io
import logging
import pathlib
import re
import subprocess
import sys
import textwrap

import pytest

from smartapi_mcp.log import (
    DATE_FORMAT,
    LOGGER_NAME,
    ColorFormatter,
    configure_logging,
    get_format,
)

# 2026-09-02 19:22:47.774 | WARNING | smartapi_mcp.server:fn:12 - message
LINE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} \| (\w+) \| "
    r"([\w.]+):([\w<>]+):(\d+) - (.*)$"
)


@pytest.fixture
def package_logger():
    """Restore the package logger's state around each test."""
    logger = logging.getLogger(LOGGER_NAME)
    saved = (list(logger.handlers), logger.level, logger.propagate)
    yield logger
    logger.handlers[:] = saved[0]
    logger.setLevel(saved[1])
    logger.propagate = saved[2]


def _in_fresh_interpreter(body: str) -> str:
    """Run ``body`` in a new interpreter and return its stdout.

    Import-time behaviour cannot be observed from inside the test session: the
    package is already imported at collection time, pytest attaches its own
    capture handlers, and other tests legitimately call ``configure_logging``.
    A subprocess is the only place these properties are actually visible.
    """
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(body)],
        capture_output=True,
        text=True,
        check=False,
        cwd=pathlib.Path(__file__).resolve().parent.parent,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


class TestLibraryHygiene:
    """The reason this module exists."""

    def test_importing_the_package_adds_only_a_null_handler(self):
        """Import must not attach anything that writes."""
        out = _in_fresh_interpreter("""
            import logging
            import smartapi_mcp  # noqa: F401
            handlers = logging.getLogger("smartapi_mcp").handlers
            print("null:", any(isinstance(h, logging.NullHandler) for h in handlers))
            print("writing:", [type(h).__name__ for h in handlers
                               if not isinstance(h, logging.NullHandler)])
        """)
        assert "null: True" in out
        assert "writing: []" in out

    def test_importing_the_package_leaves_the_root_logger_alone(self):
        """A host's own configuration must survive our import.

        Under loguru this failed: importing the package called
        ``logger.remove()`` on loguru's single global logger, removing the
        host's sinks and redirecting its records into our stderr handler.
        """
        out = _in_fresh_interpreter("""
            import logging, sys
            logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                                format="APP|%(name)s|%(message)s", force=True)
            before = list(logging.getLogger().handlers)
            import smartapi_mcp  # noqa: F401
            after = list(logging.getLogger().handlers)
            print("root_unchanged:", before == after)
            logging.getLogger("host").info("host still logging")
        """)
        assert "root_unchanged: True" in out
        assert "APP|host|host still logging" in out

    def test_records_propagate_to_the_host_until_we_configure(self):
        """Unconfigured, our records should reach the application's handlers."""
        out = _in_fresh_interpreter("""
            import logging, sys
            logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                                format="HOST|%(name)s|%(message)s", force=True)
            import smartapi_mcp  # noqa: F401
            logging.getLogger("smartapi_mcp.server").warning("a library warning")
        """)
        assert "HOST|smartapi_mcp.server|a library warning" in out

    def test_configure_logging_stops_propagating_to_the_host(self):
        """Once we own a handler, records must not also hit the root logger."""
        out = _in_fresh_interpreter("""
            import logging, sys
            logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                                format="HOST|%(message)s", force=True)
            from smartapi_mcp.log import configure_logging
            configure_logging("DEBUG", stream=sys.stdout)
            logging.getLogger("smartapi_mcp.x").warning("once only")
        """)
        assert out.count("once only") == 1, out
        assert "HOST|once only" not in out


class TestConfigureLogging:
    def test_installs_one_handler_and_sets_the_level(self, package_logger):
        stream = io.StringIO()
        configure_logging("DEBUG", stream=stream)
        ours = [
            h for h in package_logger.handlers if getattr(h, "_smartapi_mcp", False)
        ]
        assert len(ours) == 1
        assert package_logger.level == logging.DEBUG

    def test_is_idempotent(self, package_logger):
        """The CLI calls it once per --log-level; output must not double up."""
        stream = io.StringIO()
        configure_logging("INFO", stream=stream)
        configure_logging("INFO", stream=stream)
        ours = [
            h for h in package_logger.handlers if getattr(h, "_smartapi_mcp", False)
        ]
        assert len(ours) == 1
        logging.getLogger(f"{LOGGER_NAME}.x").info("once")
        assert stream.getvalue().count("once") == 1

    def test_level_is_respected(self, package_logger):
        stream = io.StringIO()
        configure_logging("WARNING", stream=stream)
        log = logging.getLogger(f"{LOGGER_NAME}.x")
        log.info("suppressed")
        log.warning("kept")
        out = stream.getvalue()
        assert "suppressed" not in out
        assert "kept" in out

    def test_output_matches_the_documented_format(self, package_logger):
        """Format parity with the loguru sink used through 0.5.0."""
        stream = io.StringIO()
        configure_logging("INFO", stream=stream, color=False)

        def emit():
            logging.getLogger(f"{LOGGER_NAME}.server").warning("a message")

        emit()
        m = LINE_RE.match(stream.getvalue().strip())
        assert m, f"unexpected format: {stream.getvalue()!r}"
        level, name, func, _line, message = m.groups()
        assert level == "WARNING"
        assert name == "smartapi_mcp.server"  # full dotted module, as loguru gave
        assert func == "emit"  # the real call site, not a wrapper
        assert message == "a message"

    def test_percent_style_arguments_are_interpolated(self, package_logger):
        """loguru used brace formatting, so %-style args were dropped silently.

        The CLI's signal handler logs ``"Received signal %s", sig``; under
        loguru that printed a literal ``%s`` and lost the signal number.
        """
        stream = io.StringIO()
        configure_logging("DEBUG", stream=stream, color=False)
        logging.getLogger(f"{LOGGER_NAME}.cli").debug("Received signal %s", 15)
        assert "Received signal 15" in stream.getvalue()
        assert "%s" not in stream.getvalue()

    def test_colour_is_off_for_a_non_tty_by_default(self, package_logger):
        stream = io.StringIO()  # no isatty() -> no colour
        configure_logging("INFO", stream=stream)
        logging.getLogger(f"{LOGGER_NAME}.x").info("plain")
        assert "\033[" not in stream.getvalue()

    def test_colour_can_be_forced_on(self, package_logger):
        stream = io.StringIO()
        configure_logging("INFO", stream=stream, color=True)
        logging.getLogger(f"{LOGGER_NAME}.x").warning("bright")
        out = stream.getvalue()
        assert "\033[32m" in out  # green timestamp
        assert "\033[33m" in out  # yellow WARNING
        assert out.endswith("\033[0m\n")


class TestFormatter:
    def test_get_format_is_a_logging_format_string(self):
        fmt = get_format()
        assert "%(levelname)s" in fmt
        assert "%(name)s" in fmt
        assert "%(funcName)s" in fmt
        assert "%(lineno)d" in fmt

    def test_a_message_containing_the_separator_is_not_mangled(self):
        """The colour path re-splits the rendered line, so ' - ' in a message
        must not confuse it."""
        record = logging.LogRecord(
            "smartapi_mcp.x",
            logging.INFO,
            __file__,
            1,
            "a - b | c",
            None,
            None,
            func="fn",
        )
        plain = ColorFormatter(color=False).format(record)
        colored = ColorFormatter(color=True).format(record)
        assert plain.endswith("a - b | c")
        assert "a - b | c" in colored.replace("\033[0m", "").replace("\033[1m", "")

    def test_date_format_has_no_subsecond_directive(self):
        """Milliseconds come from %(msecs)03d, not from datefmt."""
        assert "%f" not in DATE_FORMAT

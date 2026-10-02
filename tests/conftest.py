"""Shared test fixtures."""

import logging

import pytest

from smartapi_mcp.log import LOGGER_NAME, THIRD_PARTY_LOGGERS


@pytest.fixture(autouse=True)
def _restore_logging():
    """Undo any ``configure_logging`` a test triggers, e.g. through ``cli.main``.

    It turns off propagation on the package logger, which would otherwise leak
    into later tests and hide records from ``caplog`` (which listens at the
    root logger).
    """
    loggers = [logging.getLogger(n) for n in (LOGGER_NAME, *THIRD_PARTY_LOGGERS)]
    saved = [(list(lg.handlers), lg.level, lg.propagate) for lg in loggers]
    yield
    for lg, (handlers, level, propagate) in zip(loggers, saved, strict=True):
        lg.handlers[:] = handlers
        lg.setLevel(level)
        lg.propagate = propagate

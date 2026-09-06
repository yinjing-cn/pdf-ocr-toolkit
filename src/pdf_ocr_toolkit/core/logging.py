"""Centralised logging configuration.

Every module obtains its logger through :func:`get_logger` so that log levels,
formatting and handlers are configured in a single place.
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str | int = logging.INFO) -> None:
    """Configure root logging once.

    Calling this function multiple times is safe; subsequent calls only
    adjust the level on the shared stream handler.
    """
    global _CONFIGURED

    root = logging.getLogger()
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
        root.addHandler(handler)
        _CONFIGURED = True

    root.setLevel(level)
    for handler in root.handlers:
        handler.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger, initialising logging with defaults if needed."""
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(name)

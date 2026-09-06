"""Core infrastructure: configuration, logging and the parser registry."""

from pdf_ocr_toolkit.core.config import Settings, get_settings
from pdf_ocr_toolkit.core.logging import get_logger, setup_logging
from pdf_ocr_toolkit.core.registry import ParserRegistry, register_parser, registry

__all__ = [
    "Settings",
    "get_settings",
    "get_logger",
    "setup_logging",
    "ParserRegistry",
    "register_parser",
    "registry",
]

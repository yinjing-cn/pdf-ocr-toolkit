"""Parser registry with a decorator-based registration mechanism.

Third-party code can add support for a new document type by subclassing
:class:`~pdf_ocr_toolkit.pipeline.base_parser.BaseParser` and decorating it
with ``@register_parser("my_doc_type")``.  The registry is process-global and
also exposes metadata (human-readable label and supported file hints) used by
the CLI and API.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Type

from pdf_ocr_toolkit.core.logging import get_logger
from pdf_ocr_toolkit.pipeline.base_parser import BaseParser

logger = get_logger(__name__)


class ParserRegistry:
    """A process-wide registry mapping document-type keys to parser classes."""

    def __init__(self) -> None:
        self._parsers: Dict[str, Type[BaseParser]] = {}

    def register(self, key: str, parser_cls: Type[BaseParser]) -> None:
        """Register ``parser_cls`` under ``key``.

        :raises ValueError: if ``key`` is already registered to a different class.
        """
        key = key.strip().lower()
        if not key:
            raise ValueError("Parser key must be a non-empty string.")
        existing = self._parsers.get(key)
        if existing is not None and existing is not parser_cls:
            raise ValueError(
                f"Parser key '{key}' is already registered to {existing.__name__}; "
                f"cannot override with {parser_cls.__name__}."
            )
        self._parsers[key] = parser_cls
        logger.debug("Registered parser '%s' -> %s", key, parser_cls.__name__)

    def get(self, key: str) -> Type[BaseParser]:
        """Return the parser class registered under ``key``.

        :raises KeyError: if no parser is registered for ``key``.
        """
        key = key.strip().lower()
        if key not in self._parsers:
            available = ", ".join(sorted(self._parsers)) or "<none>"
            raise KeyError(
                f"No parser registered for document type '{key}'. "
                f"Available parsers: {available}"
            )
        return self._parsers[key]

    def list_keys(self) -> List[str]:
        """Return all registered document-type keys, sorted alphabetically."""
        return sorted(self._parsers)

    def describe(self) -> List[dict]:
        """Return metadata for every registered parser (used by CLI/API help)."""
        return [
            {
                "type": key,
                "parser": cls.__name__,
                "label": getattr(cls, "label", key),
                "description": getattr(cls, "description", "") or "",
            }
            for key, cls in sorted(self._parsers.items())
        ]

    def clear(self) -> None:
        """Remove all registered parsers (primarily useful in tests)."""
        self._parsers.clear()


# Process-global singleton registry.
registry = ParserRegistry()


def register_parser(key: str) -> Callable[[Type[BaseParser]], Type[BaseParser]]:
    """Class decorator that registers a :class:`BaseParser` subclass.

    Usage::

        @register_parser("invoice")
        class InvoiceParser(BaseParser):
            ...
    """

    def _decorator(cls: Type[BaseParser]) -> Type[BaseParser]:
        if not issubclass(cls, BaseParser):
            raise TypeError(
                f"@register_parser can only decorate BaseParser subclasses, "
                f"got {cls!r}"
            )
        registry.register(key, cls)
        return cls

    return _decorator

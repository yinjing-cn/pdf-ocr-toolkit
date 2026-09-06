"""Tests for the parser registry and its decorator mechanism."""

from __future__ import annotations

import pytest

from pdf_ocr_toolkit.core.registry import ParserRegistry, register_parser, registry
from pdf_ocr_toolkit.pipeline.base_parser import BaseParser
from pdf_ocr_toolkit.pipeline.loader import Document


class _DummyParser(BaseParser):
    label = "Dummy"

    def parse(self, document: Document):  # pragma: no cover - never executed
        raise NotImplementedError


class TestGlobalRegistry:
    def test_builtin_parsers_are_registered(self) -> None:
        keys = registry.list_keys()
        assert "invoice" in keys
        assert "delivery_note" in keys

    def test_get_returns_registered_class(self) -> None:
        cls = registry.get("invoice")
        assert issubclass(cls, BaseParser)
        assert cls.label == "Generic Invoice"

    def test_get_unknown_parser_raises_with_hint(self) -> None:
        with pytest.raises(KeyError, match="No parser registered"):
            registry.get("does_not_exist")

    def test_describe_contains_metadata(self) -> None:
        descriptions = {item["type"]: item for item in registry.describe()}
        assert descriptions["invoice"]["label"] == "Generic Invoice"
        assert descriptions["delivery_note"]["parser"] == "DeliveryNoteParser"


class TestIsolatedRegistry:
    def test_register_and_retrieve(self) -> None:
        local = ParserRegistry()
        local.register("dummy", _DummyParser)
        assert local.get("dummy") is _DummyParser
        assert local.list_keys() == ["dummy"]

    def test_duplicate_registration_of_same_class_is_allowed(self) -> None:
        local = ParserRegistry()
        local.register("dummy", _DummyParser)
        local.register("dummy", _DummyParser)  # idempotent
        assert local.get("dummy") is _DummyParser

    def test_duplicate_key_with_different_class_raises(self) -> None:
        local = ParserRegistry()
        local.register("dummy", _DummyParser)
        with pytest.raises(ValueError, match="already registered"):
            local.register("dummy", type("OtherParser", (BaseParser,), {"parse": lambda s, d: None}))

    def test_register_parser_decorator_registers_class(self) -> None:
        local = ParserRegistry()

        @register_parser("decorated_doc")
        class DecoratedParser(BaseParser):
            label = "Decorated"

            def parse(self, document: Document):  # pragma: no cover
                raise NotImplementedError

        # The decorator targets the global registry.
        assert registry.get("decorated_doc") is DecoratedParser
        local.clear()

    def test_decorator_rejects_non_baseparser_subclass(self) -> None:
        with pytest.raises(TypeError, match="BaseParser subclasses"):

            @register_parser("bad_doc")
            class NotAParser:  # pragma: no cover - decoration itself fails
                pass

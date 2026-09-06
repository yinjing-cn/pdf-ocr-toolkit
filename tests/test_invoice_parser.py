"""Tests for the built-in generic invoice parser."""

from __future__ import annotations

import json
from pathlib import Path

from pdf_ocr_toolkit.core.registry import registry
from pdf_ocr_toolkit.pipeline.loader import load_document


def test_invoice_parser_extracts_header_fields(invoice_txt: Path) -> None:
    document = load_document(invoice_txt)
    parser = registry.get("invoice")()
    result = parser.parse(document)

    assert result.document_type == "invoice"
    assert result.fields["invoice_number"] == "INV-2025-0042"
    assert result.fields["invoice_date"] == "2025-03-15"
    assert result.fields["due_date"] == "2025-04-14"
    assert result.fields["currency"] == "USD"


def test_invoice_parser_extracts_parties(invoice_txt: Path) -> None:
    document = load_document(invoice_txt)
    result = registry.get("invoice")().parse(document)

    assert result.fields["seller"] == "Demo Trading Co Ltd"
    assert "Fictional Road" in result.fields["seller_address"]
    assert result.fields["buyer"] == "Acme Corp"
    assert "Riverside" not in result.fields["buyer_address"]
    assert "Example Avenue" in result.fields["buyer_address"]


def test_invoice_parser_extracts_line_items(invoice_txt: Path) -> None:
    document = load_document(invoice_txt)
    result = registry.get("invoice")().parse(document)

    assert len(result.line_items) == 4
    first = result.line_items[0]
    assert first.description == "Wireless Mouse (Demo Model)"
    assert first.quantity == 10
    assert first.unit_price == 25.0
    assert first.amount == 250.0

    total = sum(item.amount or 0 for item in result.line_items)
    assert total == 1695.00


def test_invoice_parser_extracts_totals(invoice_txt: Path) -> None:
    document = load_document(invoice_txt)
    result = registry.get("invoice")().parse(document)

    assert result.fields["subtotal"] == 1695.00
    assert result.fields["tax_rate"] == "8.5%"
    assert result.fields["tax_amount"] == 144.08
    assert result.fields["total_amount"] == 1839.08
    # The cross-check warning must not fire for consistent demo data.
    assert not result.warnings


def test_invoice_parser_matches_expected_json(invoice_txt: Path) -> None:
    """The parsed payload should match the committed expected-output sample."""
    expected_path = Path(__file__).resolve().parents[1] / "samples" / "expected_output" / "invoice_sample.json"
    document = load_document(invoice_txt)
    result = registry.get("invoice")().parse(document)

    expected_payload = json.loads(expected_path.read_text(encoding="utf-8"))
    actual = result.to_dict()
    assert actual["fields"] == expected_payload["fields"]
    assert actual["line_items"] == expected_payload["line_items"]

"""Tests for the built-in delivery-note parser."""

from __future__ import annotations

import json
from pathlib import Path

from pdf_ocr_toolkit.core.registry import registry
from pdf_ocr_toolkit.pipeline.loader import load_document


def test_delivery_note_parser_extracts_header(delivery_note_txt: Path) -> None:
    document = load_document(delivery_note_txt)
    result = registry.get("delivery_note")().parse(document)

    assert result.document_type == "delivery_note"
    assert result.fields["note_number"] == "DN-2025-1031"
    assert result.fields["delivery_date"] == "2025-03-18"
    assert result.fields["order_reference"] == "PO-7781"


def test_delivery_note_parser_extracts_parties(delivery_note_txt: Path) -> None:
    document = load_document(delivery_note_txt)
    result = registry.get("delivery_note")().parse(document)

    assert result.fields["supplier"] == "Acme Corp"
    assert "Logistics Lane" in result.fields["supplier_address"]
    assert result.fields["customer"] == "Blue River Cafe"
    assert "Riverside Walk" in result.fields["ship_to_address"]
    assert result.fields["received_by"] == "Taylor Morgan (signed)"


def test_delivery_note_parser_extracts_items(delivery_note_txt: Path) -> None:
    document = load_document(delivery_note_txt)
    result = registry.get("delivery_note")().parse(document)

    assert len(result.line_items) == 4
    cups = result.line_items[0]
    assert cups.description == "Ceramic Coffee Cup 250ml"
    assert cups.quantity == 40
    assert cups.unit_price == 4.5
    assert cups.amount is None  # delivery notes don't carry line amounts

    # A quantity-only row (no unit price) is still captured.
    stirrers = result.line_items[2]
    assert stirrers.description == "Wooden Stirrers (box of 1000)"
    assert stirrers.quantity == 5
    assert stirrers.unit_price is None

    quantities = [item.quantity for item in result.line_items]
    assert quantities == [40, 12, 5, 30]


def test_delivery_note_parser_matches_expected_json(delivery_note_txt: Path) -> None:
    expected_path = (
        Path(__file__).resolve().parents[1]
        / "samples" / "expected_output" / "delivery_note_sample.json"
    )
    document = load_document(delivery_note_txt)
    result = registry.get("delivery_note")().parse(document)

    expected_payload = json.loads(expected_path.read_text(encoding="utf-8"))
    actual = result.to_dict()
    assert actual["fields"] == expected_payload["fields"]
    assert actual["line_items"] == expected_payload["line_items"]
    assert actual["warnings"] == expected_payload["warnings"]

"""Tests for the Excel / CSV / JSON exporters."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pdf_ocr_toolkit.core.registry import registry
from pdf_ocr_toolkit.pipeline.base_parser import LineItem, ParseResult
from pdf_ocr_toolkit.pipeline.exporter import export, export_csv, export_excel, export_json
from pdf_ocr_toolkit.pipeline.loader import load_document


def _sample_result() -> ParseResult:
    return ParseResult(
        document_type="invoice",
        fields={"_title": "Invoice", "invoice_number": "INV-TEST-1", "total_amount": 100.0},
        line_items=[
            LineItem(description="Widget A", quantity=2, unit_price=10.0, amount=20.0),
            LineItem(description="Widget B", quantity=1, unit_price=80.0, amount=80.0),
        ],
    )


def test_export_json_roundtrip(tmp_path: Path) -> None:
    out = export_json(_sample_result(), tmp_path / "result.json")
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["document_type"] == "invoice"
    assert payload["fields"]["invoice_number"] == "INV-TEST-1"
    assert len(payload["line_items"]) == 2
    assert payload["line_items"][1]["description"] == "Widget B"


def test_export_csv_contains_line_items(tmp_path: Path) -> None:
    out = export_csv(_sample_result(), tmp_path / "result.csv")
    rows = list(csv.reader(out.read_text(encoding="utf-8").splitlines()))
    assert rows[0] == ["Description", "Quantity", "Unit Price", "Amount"]
    assert rows[1][0] == "Widget A"
    assert rows[2][3] == "80.0"


def test_export_excel_creates_valid_workbook(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    out = export_excel(_sample_result(), tmp_path / "result.xlsx")
    assert out.exists()

    wb = openpyxl.load_workbook(out)
    ws = wb.active
    # Header field pair: key/value.
    values = [cell.value for row in ws.iter_rows() for cell in row]
    assert "Invoice Number" in values
    assert "INV-TEST-1" in values
    # Detail table header.
    assert "Description" in values and "Amount" in values
    # Data row content.
    assert "Widget A" in values


def test_export_dispatches_by_suffix(tmp_path: Path) -> None:
    result = _sample_result()
    assert export(result, tmp_path / "a.json").suffix == ".json"
    assert export(result, tmp_path / "a.csv").suffix == ".csv"
    assert export(result, tmp_path / "a.xlsx").suffix == ".xlsx"
    with pytest.raises(ValueError, match="Unsupported export format"):
        export(result, tmp_path / "a.txt")


def test_export_real_invoice_result_to_excel(tmp_path: Path, invoice_txt: Path) -> None:
    """End-to-end: parse the fictional invoice and write a workbook."""
    openpyxl = pytest.importorskip("openpyxl")
    parsed = registry.get("invoice")().parse(load_document(invoice_txt))
    out = export(parsed, tmp_path / "invoice.xlsx")

    wb = openpyxl.load_workbook(out)
    ws = wb.active
    text_cells = [str(c.value) for row in ws.iter_rows() for c in row if c.value is not None]
    assert "INV-2025-0042" in text_cells
    assert "Wireless Mouse (Demo Model)" in text_cells
    assert "Acme Corp" in text_cells

"""End-to-end pipeline tests (synchronous mode, no external OCR)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pdf_ocr_toolkit.core.config import Settings
from pdf_ocr_toolkit.pipeline.loader import Document, PageData, load_document
from pdf_ocr_toolkit.pipeline.ocr_engine import TextLayerEngine, get_engine
from pdf_ocr_toolkit.pipeline.runner import run_pipeline
from pdf_ocr_toolkit.tasks import get_celery_app, process_document


def test_loader_reads_text_fixture(invoice_txt: Path) -> None:
    doc = load_document(invoice_txt)
    assert doc.metadata["format"] == "txt"
    assert len(doc.pages) == 1
    assert doc.has_text
    assert "INV-2025-0042" in doc.full_text


def test_loader_rejects_missing_and_unsupported(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_document(tmp_path / "nope.pdf")
    unsupported = tmp_path / "data.bin"
    unsupported.write_bytes(b"\x00\x01")
    with pytest.raises(ValueError, match="Unsupported file type"):
        load_document(unsupported)


def test_text_layer_engine_is_used_in_text_mode() -> None:
    settings = Settings(ocr_engine="text")
    engine = get_engine(settings)
    assert isinstance(engine, TextLayerEngine)
    assert engine.is_available()
    assert engine.name == "text"


def test_auto_engine_never_raises_when_deps_missing(monkeypatch) -> None:
    """Auto resolution must always return a usable engine regardless of deps."""
    from pdf_ocr_toolkit.pipeline import ocr_engine

    # Simulate an environment without any OCR dependency.
    monkeypatch.setattr(ocr_engine.TesseractEngine, "is_available", lambda self: False)
    monkeypatch.setattr(ocr_engine.PaddleEngine, "is_available", lambda self: False)
    engine = ocr_engine.get_engine(Settings(ocr_engine="auto"))
    assert isinstance(engine, TextLayerEngine)


def test_engine_warns_on_empty_document_without_ocr() -> None:
    doc = Document(path=Path("empty.pdf"), pages=[PageData(page_number=1, text="", source="empty")])
    engine = TextLayerEngine()
    result = engine.extract(doc)
    assert not result.has_text
    assert any("OCR" in warning for warning in result.warnings)


def test_run_pipeline_on_invoice_txt(tmp_path: Path, invoice_txt: Path) -> None:
    settings = Settings(output_dir=tmp_path, ocr_engine="text")
    result = run_pipeline(invoice_txt, "invoice", settings)

    assert result.fields["invoice_number"] == "INV-2025-0042"
    assert len(result.line_items) == 4
    assert result.fields["total_amount"] == 1839.08


def test_process_document_full_sync_path(tmp_path: Path, delivery_note_txt: Path) -> None:
    settings = Settings(output_dir=tmp_path, ocr_engine="text")
    out_path = tmp_path / "delivery.xlsx"
    result_path = process_document(delivery_note_txt, "delivery_note", out_path, settings)

    assert result_path.exists()
    assert result_path == out_path


def test_process_document_json_export(tmp_path: Path, invoice_txt: Path) -> None:
    settings = Settings(output_dir=tmp_path, ocr_engine="text")
    out_path = tmp_path / "invoice.json"
    process_document(invoice_txt, "invoice", out_path, settings)

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["document_type"] == "invoice"
    assert payload["fields"]["buyer"] == "Acme Corp"


def test_celery_disabled_without_broker() -> None:
    settings = Settings(celery_broker_url="", redis_url="")
    assert not settings.celery_enabled
    assert get_celery_app(settings) is None


def test_ocr_optional_imports_never_break_package() -> None:
    """Importing the package must not require any OCR dependency."""
    import importlib

    for module in [
        "pdf_ocr_toolkit",
        "pdf_ocr_toolkit.pipeline.ocr_engine",
        "pdf_ocr_toolkit.pipeline.runner",
        "pdf_ocr_toolkit.cli",
    ]:
        imported = importlib.import_module(module)
        assert imported is not None

"""Pipeline orchestration: loader -> OCR engine -> parser.

This is the single entry point used by both the CLI and the API layer, which
keeps business logic independent from the delivery mechanism.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pdf_ocr_toolkit.core.config import Settings, get_settings
from pdf_ocr_toolkit.core.logging import get_logger
from pdf_ocr_toolkit.core.registry import registry
from pdf_ocr_toolkit.pipeline.base_parser import ParseResult
from pdf_ocr_toolkit.pipeline.loader import Document, load_document
from pdf_ocr_toolkit.pipeline.ocr_engine import enrich_with_ocr

logger = get_logger(__name__)


def run_pipeline(
    path: str | Path,
    doc_type: str,
    settings: Optional[Settings] = None,
) -> ParseResult:
    """Execute the full extraction pipeline for one document.

    :param path: path to a ``.pdf`` or ``.txt`` source file.
    :param doc_type: registry key of the parser to use (e.g. ``"invoice"``).
    :param settings: optional override for application settings.
    :returns: a structured :class:`ParseResult`.
    """
    settings = settings or get_settings()
    logger.info("Pipeline start: file=%s type=%s", path, doc_type)

    # 1. Load
    document: Document = load_document(path)

    # 2. Text extraction / OCR
    document = enrich_with_ocr(document, settings)
    if not document.has_text:
        logger.error("Document contains no extractable text after OCR stage.")

    # 3. Parse
    parser_cls = registry.get(doc_type)
    parser = parser_cls()
    result = parser.parse(document)

    # Surface loader/OCR warnings to the caller as well.
    result.warnings.extend(document.warnings)
    logger.info(
        "Pipeline finished: %s field(s), %s line item(s), %s warning(s).",
        len(result.fields),
        len(result.line_items),
        len(result.warnings),
    )
    return result

"""OCR / text-extraction stage with pluggable engines.

Engine strategy:

* :class:`TextLayerEngine` — the default.  It simply keeps the embedded text
  layer extracted by :mod:`pdfplumber`; no third-party OCR dependency needed.
* :class:`TesseractEngine` — renders PDF pages to images via *pdf2image* and
  runs *pytesseract*.  Optional, installed through ``requirements-ocr.txt``.
* :class:`PaddleEngine` — uses *PaddleOCR*.  Optional, installed through the
  ``paddle`` extra.

The important contract is **graceful degradation**: importing this module
never requires an OCR dependency.  An engine only fails at *use* time, with a
clear installation hint, so the toolkit always stays importable.
"""

from __future__ import annotations

import abc
from pathlib import Path
from typing import List

from pdf_ocr_toolkit.core.config import Settings, get_settings
from pdf_ocr_toolkit.core.logging import get_logger
from pdf_ocr_toolkit.pipeline.loader import Document

logger = get_logger(__name__)


class OCREngine(abc.ABC):
    """Abstract interface for text-extraction engines."""

    name: str = "base"

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Return True when the engine's runtime dependencies are importable."""

    @abc.abstractmethod
    def extract(self, document: Document) -> Document:
        """Populate missing page text, mutating and returning ``document``."""


class TextLayerEngine(OCREngine):
    """No-op engine that relies on the PDF's embedded text layer."""

    name = "text"

    def is_available(self) -> bool:
        return True

    def extract(self, document: Document) -> Document:
        if not document.has_text:
            document.warnings.append(
                "No embedded text layer found and no OCR engine configured. "
                "Install OCR extras (`pip install -r requirements-ocr.txt`) "
                "to process scanned/image-only PDFs."
            )
            logger.warning(document.warnings[-1])
        return document


class TesseractEngine(OCREngine):
    """OCR engine backed by pytesseract + pdf2image (requires Tesseract)."""

    name = "tesseract"

    def __init__(self, language: str = "eng", dpi: int = 300) -> None:
        self.language = language
        self.dpi = dpi

    def is_available(self) -> bool:
        try:
            import pytesseract  # noqa: F401
            import pdf2image  # noqa: F401
        except ImportError:
            return False
        return True

    def extract(self, document: Document) -> Document:
        if not self.is_available():
            hint = (
                "Tesseract OCR is not available. Install the optional OCR "
                "dependencies with `pip install -r requirements-ocr.txt` and "
                "make sure the Tesseract binary is on your PATH."
            )
            document.warnings.append(hint)
            logger.warning(hint)
            return document

        import pytesseract
        from pdf2image import convert_from_path

        target_pages = [p for p in document.pages if not p.text.strip()]
        if not target_pages:
            logger.debug("Tesseract: all pages already have text; nothing to do.")
            return document

        logger.info("Running Tesseract OCR on %s page(s) ...", len(target_pages))
        images = convert_from_path(str(document.path), dpi=self.dpi)
        for page in target_pages:
            image = images[page.page_number - 1]
            page.text = pytesseract.image_to_string(image, lang=self.language)
            page.source = "ocr"
        return document


class PaddleEngine(OCREngine):
    """OCR engine backed by PaddleOCR (optional extra ``paddle``)."""

    name = "paddle"

    def __init__(self, language: str = "en") -> None:
        self.language = language
        self._ocr = None

    def is_available(self) -> bool:
        try:
            import paddleocr  # noqa: F401
        except ImportError:
            return False
        return True

    def extract(self, document: Document) -> Document:
        if not self.is_available():
            hint = (
                "PaddleOCR is not available. Install it with "
                "`pip install 'pdf-ocr-toolkit[paddle]'`."
            )
            document.warnings.append(hint)
            logger.warning(hint)
            return document

        import numpy as np
        from pdf2image import convert_from_path
        from paddleocr import PaddleOCR

        if self._ocr is None:
            self._ocr = PaddleOCR(use_angle_cls=True, lang=self.language)

        target_pages = [p for p in document.pages if not p.text.strip()]
        if not target_pages:
            return document

        logger.info("Running PaddleOCR on %s page(s) ...", len(target_pages))
        images = convert_from_path(str(document.path), dpi=300)
        for page in target_pages:
            image = np.array(images[page.page_number - 1])
            result = self._ocr.ocr(image, cls=True)
            lines: List[str] = []
            for block in result or []:
                for line in block or []:
                    if line and len(line) >= 2:
                        lines.append(line[1][0])
            page.text = "\n".join(lines)
            page.source = "ocr"
        return document


def get_engine(settings: Settings | None = None) -> OCREngine:
    """Resolve and construct the OCR engine described by ``settings``.

    ``auto`` (the default) returns a Tesseract engine when its dependencies
    are importable, otherwise it silently falls back to the text-layer engine.
    """
    settings = settings or get_settings()
    choice = settings.ocr_engine

    if choice == "text":
        return TextLayerEngine()
    if choice == "tesseract":
        return TesseractEngine(language=settings.ocr_language, dpi=settings.ocr_dpi)
    if choice == "paddle":
        return PaddleEngine(language="ch" if settings.ocr_language.startswith("ch") else "en")

    # auto: prefer real OCR when available, else the text layer.
    tesseract = TesseractEngine(language=settings.ocr_language, dpi=settings.ocr_dpi)
    if tesseract.is_available():
        logger.info("Auto mode: using Tesseract OCR engine.")
        return tesseract
    paddle = PaddleEngine()
    if paddle.is_available():
        logger.info("Auto mode: using PaddleOCR engine.")
        return paddle
    logger.info("Auto mode: no OCR dependencies found; using embedded text layer only.")
    return TextLayerEngine()


def enrich_with_ocr(document: Document, settings: Settings | None = None) -> Document:
    """Convenience wrapper: resolve the engine and run it over ``document``."""
    engine = get_engine(settings)
    logger.debug("OCR engine resolved: %s", engine.name)
    return engine.extract(document)

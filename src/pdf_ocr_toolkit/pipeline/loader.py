"""Loader stage: turn a file on disk into a :class:`Document`.

The loader is format-aware:

* ``.pdf`` files are opened with *pdfplumber*.  Every page yields its embedded
  text layer plus page geometry.  Pages that contain no text layer (scanned
  images) are left empty here and handed to the OCR stage later.
* ``.txt`` files are loaded as a single page — handy for tests and for
  piping pre-extracted text through the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from pdf_ocr_toolkit.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PageData:
    """A single page of a source document."""

    page_number: int
    text: str = ""
    width: float = 0.0
    height: float = 0.0
    source: str = "text"  # one of: "text" (embedded layer), "ocr", "empty"


@dataclass
class Document:
    """A loaded document: pages plus metadata and non-fatal warnings."""

    path: Path
    pages: List[PageData] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Concatenated text of all pages, joined by newlines."""
        return "\n".join(page.text for page in self.pages if page.text)

    @property
    def has_text(self) -> bool:
        """True when at least one page carries extractable text."""
        return any(page.text.strip() for page in self.pages)


def load_pdf(path: Path) -> Document:
    """Load a PDF file, extracting the embedded text layer of every page."""
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - pdfplumber is a core dep
        raise RuntimeError(
            "pdfplumber is required to load PDF files. Install it with "
            "`pip install pdfplumber`."
        ) from exc

    path = Path(path)
    doc = Document(path=path, metadata={"format": "pdf"})
    logger.info("Loading PDF: %s", path)

    with pdfplumber.open(str(path)) as pdf:
        doc.metadata["page_count"] = len(pdf.pages)
        doc.metadata.setdefault("filename", path.name)
        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            source = "text" if text.strip() else "empty"
            doc.pages.append(
                PageData(
                    page_number=index,
                    text=text,
                    width=float(page.width or 0.0),
                    height=float(page.height or 0.0),
                    source=source,
                )
            )
            if source == "empty":
                logger.warning("Page %s has no text layer (likely a scanned image).", index)

    logger.info(
        "Loaded %s page(s); %s page(s) contain text.",
        len(doc.pages),
        sum(1 for p in doc.pages if p.text.strip()),
    )
    return doc


def load_text(path: Path) -> Document:
    """Load a plain-text file as a single-page document."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    return Document(
        path=path,
        pages=[PageData(page_number=1, text=text, source="text")],
        metadata={"format": "txt", "filename": path.name},
    )


def load_document(path: str | Path) -> Document:
    """Dispatch to the right loader based on the file suffix.

    :raises FileNotFoundError: if ``path`` does not exist.
    :raises ValueError: if the suffix is not supported.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return load_pdf(path)
    if suffix in {".txt", ".text"}:
        return load_text(path)
    raise ValueError(
        f"Unsupported file type '{suffix}'. Supported: .pdf, .txt"
    )

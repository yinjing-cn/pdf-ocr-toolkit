"""pdf-ocr-toolkit — A pluggable PDF OCR toolkit for structured business documents.

Turn scanned invoices, delivery notes and similar PDFs into Excel/CSV/JSON.
Ships with a parser registry, a layered pipeline and an optional FastAPI service.
"""

__version__ = "0.1.0"

# Eagerly import the parser package so that @register_parser decorators run
# and the built-in parsers are registered on package import.
from pdf_ocr_toolkit.parsers import *  # noqa: F401, F403  (re-export registration side-effects)

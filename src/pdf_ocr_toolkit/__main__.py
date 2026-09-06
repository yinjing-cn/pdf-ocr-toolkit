"""Support ``python -m pdf_ocr_toolkit`` as an alias for the ``pdf-ocr`` CLI."""

from pdf_ocr_toolkit.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

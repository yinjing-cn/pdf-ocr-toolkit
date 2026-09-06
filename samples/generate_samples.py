#!/usr/bin/env python3
"""Generate fictional demo PDFs for pdf-ocr-toolkit.

The script reads the canonical fixture text files under ``samples/fixtures``
and renders each one to a PDF with a monospaced font, preserving the column
alignment that the demo parsers expect.  A copy of each text file is also
placed next to the generated PDFs (handy for quick CLI tests).

Usage::

    python samples/generate_samples.py [--out samples/generated]

Dependencies: reportlab (``pip install -r requirements-dev.txt``).
All data is entirely fictional.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = SCRIPT_DIR / "fixtures"

SAMPLES = [
    ("invoice_sample", "Demo Trading Co Ltd — Generic Invoice"),
    ("delivery_note_sample", "Acme Corp — Delivery Note"),
]


def render_pdf(txt_path: Path, pdf_path: Path, title: str) -> None:
    """Render a plain-text fixture into a simple, text-layer PDF."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    lines = txt_path.read_text(encoding="utf-8").splitlines()
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    c.setTitle(title)
    c.setFont("Courier", 10)

    width, height = A4
    x, y = 48.0, height - 56.0
    line_height = 13.0
    bottom_margin = 56.0

    for line in lines:
        if y < bottom_margin:
            c.showPage()
            c.setFont("Courier", 10)
            y = height - 56.0
        c.drawString(x, y, line)
        y -= line_height

    c.showPage()
    c.save()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate fictional demo PDFs.")
    parser.add_argument(
        "--out",
        default=str(SCRIPT_DIR / "generated"),
        help="Output directory (default: samples/generated).",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for stem, title in SAMPLES:
        txt_path = FIXTURES_DIR / f"{stem}.txt"
        if not txt_path.exists():
            raise FileNotFoundError(f"Fixture not found: {txt_path}")

        pdf_path = out_dir / f"{stem}.pdf"
        render_pdf(txt_path, pdf_path, title)
        shutil.copyfile(txt_path, out_dir / f"{stem}.txt")
        print(f"  ✓ {pdf_path.relative_to(SCRIPT_DIR.parent) if out_dir.is_relative_to(SCRIPT_DIR.parent) else pdf_path}")

    print(f"\nGenerated {len(SAMPLES)} demo document(s) in {out_dir}")
    print("All content is fictional and safe to share.")


if __name__ == "__main__":
    main()

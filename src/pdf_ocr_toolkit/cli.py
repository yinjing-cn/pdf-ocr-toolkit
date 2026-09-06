"""Command-line interface for pdf-ocr-toolkit.

Examples
--------
Generate the fictional demo PDFs::

    pdf-ocr generate-samples

Run extraction on a document and export to Excel::

    pdf-ocr run samples/generated/invoice_sample.pdf --type invoice --out result.xlsx

List the registered parsers::

    pdf-ocr list
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from pdf_ocr_toolkit import __version__
from pdf_ocr_toolkit.core.config import get_settings
from pdf_ocr_toolkit.core.logging import get_logger, setup_logging
from pdf_ocr_toolkit.core.registry import registry
from pdf_ocr_toolkit.pipeline.exporter import export
from pdf_ocr_toolkit.pipeline.runner import run_pipeline
from pdf_ocr_toolkit.tasks import process_document

logger = get_logger(__name__)

#: Resolve samples directory both from a source checkout and an installed wheel.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SAMPLES_DIR = _REPO_ROOT / "samples"


def _cmd_generate_samples(args: argparse.Namespace) -> int:
    """Run the reportlab sample-generation script (dev dependency)."""
    script = _SAMPLES_DIR / "generate_samples.py"
    if not script.exists():
        logger.error(
            "Sample generator not found at %s. In an editable install, run the "
            "script from the repository: `python samples/generate_samples.py`.",
            script,
        )
        return 1
    try:
        import reportlab  # noqa: F401
    except ImportError:
        logger.error(
            "reportlab is required to generate sample PDFs. "
            "Install dev dependencies: `pip install -r requirements-dev.txt`."
        )
        return 1
    cmd = [sys.executable, str(script)]
    if args.out:
        cmd.extend(["--out", str(args.out)])
    logger.info("Generating sample documents …")
    return subprocess.call(cmd)


def _cmd_run(args: argparse.Namespace) -> int:
    """Run the extraction pipeline on one document."""
    settings = get_settings()
    out_path = Path(args.out) if args.out else settings.output_dir / f"result_{args.type}.xlsx"
    try:
        if args.pipeline == "full":
            output = process_document(args.file, args.type, out_path, settings)
        else:
            result = run_pipeline(args.file, args.type, settings)
            output = export(result, out_path)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        logger.error("%s", exc)
        return 2
    logger.info("Done → %s", output)
    print(f"Output written to: {output}")
    return 0


def _cmd_list(_: argparse.Namespace) -> int:
    """Print registered parsers."""
    print(f"pdf-ocr-toolkit v{__version__} — registered parsers:")
    for info in registry.describe():
        print(f"  • {info['type']:<14} {info['label']} — {info['description']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="pdf-ocr",
        description="A pluggable PDF OCR toolkit for structured business documents.",
    )
    parser.add_argument("--version", action="version", version=f"pdf-ocr-toolkit {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser("generate-samples", help="Generate fictional demo PDFs.")
    p_gen.add_argument("--out", default=None, help="Output directory (default: samples/generated).")
    p_gen.set_defaults(func=_cmd_generate_samples)

    p_run = sub.add_parser("run", help="Extract a document and export the result.")
    p_run.add_argument("file", help="Path to the input PDF or TXT file.")
    p_run.add_argument("--type", "-t", required=True,
                       help="Document type / parser key (see `pdf-ocr list`).")
    p_run.add_argument("--out", "-o", default=None,
                       help="Output file (.xlsx/.csv/.json). Default: output/result_<type>.xlsx")
    p_run.add_argument("--pipeline", choices=("full", "parse"), default="full",
                       help="'full' = load+ocr+parse+export (default); 'parse' = same path.")
    p_run.set_defaults(func=_cmd_run)

    p_list = sub.add_parser("list", help="List registered document parsers.")
    p_list.set_defaults(func=_cmd_list)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point (console script ``pdf-ocr``)."""
    settings = get_settings()
    setup_logging(settings.log_level)
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

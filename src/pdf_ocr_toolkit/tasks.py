"""Task layer: document processing with an optional Celery backend.

The synchronous :func:`process_document` is always available.  When a broker
URL is configured *and* Celery is installed, :func:`get_celery_app` exposes a
Celery application whose ``pdf_ocr_toolkit.process`` task wraps the same
function — so sync and async paths share one code path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pdf_ocr_toolkit.core.config import Settings, get_settings
from pdf_ocr_toolkit.core.logging import get_logger
from pdf_ocr_toolkit.pipeline.exporter import export
from pdf_ocr_toolkit.pipeline.runner import run_pipeline

logger = get_logger(__name__)


def process_document(
    input_path: str | Path,
    doc_type: str,
    out_path: str | Path,
    settings: Optional[Settings] = None,
) -> Path:
    """Run loader -> OCR -> parser -> exporter synchronously.

    :returns: the path of the exported file.
    """
    settings = settings or get_settings()
    logger.info("Processing document: %s (type=%s) -> %s", input_path, doc_type, out_path)
    result = run_pipeline(input_path, doc_type, settings)
    return export(result, out_path)


def get_celery_app(settings: Optional[Settings] = None):
    """Build and return a Celery app, or ``None`` when async is unavailable.

    Celery is imported lazily so that the toolkit never requires a running
    broker (or even the celery package at import time) to function.
    """
    settings = settings or get_settings()
    if not settings.celery_enabled:
        logger.info("No broker URL configured; Celery async mode disabled.")
        return None
    try:
        from celery import Celery
    except ImportError:  # pragma: no cover - celery is a core dep in practice
        logger.warning("celery package not importable; async tasks disabled.")
        return None

    broker = settings.effective_broker_url
    app = Celery(
        "pdf_ocr_toolkit",
        broker=broker,
        backend=settings.celery_result_backend or broker,
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_track_started=True,
    )

    @app.task(name="pdf_ocr_toolkit.process", bind=True)
    def process_task(self, input_path: str, doc_type: str, out_path: str) -> str:
        """Celery wrapper around :func:`process_document`."""
        output = process_document(input_path, doc_type, out_path, settings)
        return str(output)

    # Expose the task on the app for convenient access.
    app.process_task = process_task  # type: ignore[attr-defined]
    logger.info("Celery app created (broker=%s)", broker)
    return app

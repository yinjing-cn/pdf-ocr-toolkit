"""FastAPI application: upload PDFs, run extraction, download results.

Endpoints
---------
``GET  /``                 Minimal browser upload page.
``GET  /health``           Liveness probe + engine/parser info.
``GET  /api/parsers``      List registered document parsers.
``POST /api/jobs``         Upload a PDF and create an extraction job.
``GET  /api/jobs/{id}``    Query job status and parsed preview.
``GET  /api/jobs/{id}/download``   Download the exported file.

When a Celery broker is configured jobs are enqueued as async tasks; without
a broker the same work runs synchronously and the job is already finished
when the response returns — no Redis required to try the toolkit.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from pdf_ocr_toolkit import __version__
from pdf_ocr_toolkit.core.config import get_settings
from pdf_ocr_toolkit.core.logging import get_logger, setup_logging
from pdf_ocr_toolkit.core.registry import registry
from pdf_ocr_toolkit.pipeline.exporter import export
from pdf_ocr_toolkit.pipeline.runner import run_pipeline
from pdf_ocr_toolkit.tasks import get_celery_app

logger = get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"

JobStatus = Literal["pending", "processing", "done", "failed"]


@dataclass
class JobRecord:
    """In-memory record for an extraction job (demo/lightweight use)."""

    id: str
    filename: str
    doc_type: str
    status: JobStatus = "pending"
    created_at: datetime = field(default_factory=datetime.utcnow)
    result_path: Optional[Path] = None
    result_format: str = "xlsx"
    error: Optional[str] = None
    preview: Optional[dict] = None


def create_app() -> FastAPI:
    """Application factory — keeps construction explicit and test-friendly."""
    settings = get_settings()
    setup_logging(settings.log_level)

    upload_dir = settings.output_dir / "uploads"
    results_dir = settings.output_dir / "results"
    upload_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title="pdf-ocr-toolkit API",
        version=__version__,
        description="Upload scanned business PDFs and get structured Excel/CSV/JSON back.",
    )
    jobs: Dict[str, JobRecord] = {}
    jobs_lock = threading.Lock()
    celery_app = get_celery_app(settings)

    # ------------------------------------------------------------------ #
    def _run_job(job: JobRecord, input_path: Path) -> None:
        """Execute pipeline + export for one job (used in sync mode)."""
        try:
            job.status = "processing"
            parsed = run_pipeline(input_path, job.doc_type, settings)
            out_path = results_dir / f"{job.id}.{job.result_format}"
            export(parsed, out_path)
            job.result_path = out_path
            job.preview = parsed.to_dict()
            job.status = "done"
        except Exception as exc:  # noqa: BLE001 - surface any failure to the job record
            logger.exception("Job %s failed", job.id)
            job.status = "failed"
            job.error = str(exc)

    # ------------------------------------------------------------------ #
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index() -> HTMLResponse:
        """Serve the minimal upload page."""
        html = (_TEMPLATES_DIR / "upload.html").read_text(encoding="utf-8")
        return HTMLResponse(html)

    @app.get("/health")
    def health() -> dict:
        """Liveness probe with runtime configuration summary."""
        return {
            "status": "ok",
            "version": __version__,
            "ocr_engine": settings.ocr_engine,
            "async_mode": bool(celery_app),
            "parsers": registry.list_keys(),
        }

    @app.get("/api/parsers")
    def list_parsers() -> dict:
        """List all registered parsers and their metadata."""
        return {"parsers": registry.describe()}

    @app.post("/api/jobs", status_code=201)
    async def create_job(
        file: UploadFile = File(..., description="PDF or TXT document to process"),
        doc_type: str = Form("invoice", description="Registered parser key"),
        fmt: str = Form("xlsx", description="Export format: xlsx | csv | json"),
    ) -> dict:
        """Upload a document and start an extraction job."""
        if fmt not in {"xlsx", "csv", "json"}:
            raise HTTPException(status_code=400, detail="fmt must be one of xlsx, csv, json")
        try:
            registry.get(doc_type)
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        suffix = Path(file.filename or "upload.pdf").suffix or ".pdf"
        job_id = uuid.uuid4().hex[:12]
        input_path = upload_dir / f"{job_id}{suffix}"

        size = 0
        with input_path.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.api_upload_limit_mb * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="File exceeds upload size limit.")
                handle.write(chunk)

        job = JobRecord(id=job_id, filename=file.filename or input_path.name,
                        doc_type=doc_type, result_format=fmt)
        with jobs_lock:
            jobs[job_id] = job

        if celery_app is not None:
            async_result = celery_app.process_task.delay(
                str(input_path), doc_type, str(results_dir / f"{job_id}.{fmt}")
            )
            job.preview = {"celery_task_id": async_result.id}
        else:
            _run_job(job, input_path)

        return {"job_id": job_id, "status": job.status, "async": bool(celery_app)}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict:
        """Return job status and (when done) a parsed-field preview."""
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        return {
            "job_id": job.id,
            "filename": job.filename,
            "doc_type": job.doc_type,
            "status": job.status,
            "created_at": job.created_at.isoformat() + "Z",
            "error": job.error,
            "preview": job.preview,
        }

    @app.get("/api/jobs/{job_id}/download")
    def download_job(job_id: str) -> FileResponse:
        """Download the exported result file."""
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        if job.status != "done" or not job.result_path or not job.result_path.exists():
            raise HTTPException(status_code=409, detail=f"Job is not ready (status={job.status}).")
        media = {
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "csv": "text/csv",
            "json": "application/json",
        }[job.result_format]
        return FileResponse(
            job.result_path,
            media_type=media,
            filename=f"result_{job.doc_type}_{job.id}.{job.result_format}",
        )

    return app


app = create_app()

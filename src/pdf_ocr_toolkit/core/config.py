"""Application configuration via pydantic-settings.

All settings can be overridden through environment variables prefixed with
``PDF_OCR_`` (e.g. ``PDF_OCR_LOG_LEVEL=DEBUG``).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings with sensible defaults."""

    model_config = SettingsConfigDict(
        env_prefix="PDF_OCR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    output_dir: Path = Field(default=Path("./output"))

    # --- OCR engine ---
    # "auto"  → use text-layer extraction; fall back to OCR for image-only pages
    # "text"  → text layer only (pdfplumber); never invoke OCR
    # "tesseract" / "paddle" → force the respective OCR engine
    ocr_engine: Literal["auto", "text", "tesseract", "paddle"] = "auto"
    ocr_language: str = "eng"
    ocr_dpi: int = Field(default=300, ge=72, le=600)

    # --- Task queue (optional) ---
    # When empty the pipeline runs synchronously in-process.
    redis_url: str = ""
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_upload_limit_mb: int = 20

    @property
    def celery_enabled(self) -> bool:
        """Return True when a broker URL is configured for async tasks."""
        return bool(self.celery_broker_url or self.redis_url)

    @property
    def effective_broker_url(self) -> str:
        """Resolve the Celery broker URL, falling back to ``redis_url``."""
        return self.celery_broker_url or self.redis_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance (process-wide singleton)."""
    return Settings()

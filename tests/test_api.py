"""Smoke tests for the FastAPI layer (synchronous, in-process)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pdf_ocr_toolkit.api.main import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    """A TestClient wrapping the synchronously-configured FastAPI app."""
    app = create_app()
    return TestClient(app)


def test_health_reports_parsers(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "invoice" in body["parsers"]
    assert "delivery_note" in body["parsers"]
    assert body["async_mode"] is False


def test_parsers_listing(client: TestClient) -> None:
    resp = client.get("/api/parsers")
    assert resp.status_code == 200
    types = {p["type"] for p in resp.json()["parsers"]}
    assert {"invoice", "delivery_note"} <= types


def test_index_page_served(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "pdf-ocr-toolkit" in resp.text


def test_full_job_flow_with_txt(client: TestClient, invoice_txt) -> None:
    with open(invoice_txt, "rb") as handle:
        create = client.post(
            "/api/jobs",
            files={"file": ("invoice.txt", handle, "text/plain")},
            data={"doc_type": "invoice", "fmt": "json"},
        )
    assert create.status_code == 201
    job_id = create.json()["job_id"]

    status = client.get(f"/api/jobs/{job_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "done"
    assert body["preview"]["fields"]["invoice_number"] == "INV-2025-0042"
    assert len(body["preview"]["line_items"]) == 4

    download = client.get(f"/api/jobs/{job_id}/download")
    assert download.status_code == 200
    assert download.content  # non-empty file payload


def test_unknown_doc_type_rejected(client: TestClient, invoice_txt) -> None:
    with open(invoice_txt, "rb") as handle:
        resp = client.post(
            "/api/jobs",
            files={"file": ("x.txt", handle, "text/plain")},
            data={"doc_type": "nonexistent", "fmt": "json"},
        )
    assert resp.status_code == 400
    assert "No parser registered" in resp.json()["detail"]


def test_unknown_job_returns_404(client: TestClient) -> None:
    assert client.get("/api/jobs/doesnotexist").status_code == 404

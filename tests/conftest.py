"""Shared pytest fixtures: paths to the fictional sample documents."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "samples" / "fixtures"
EXPECTED = REPO_ROOT / "samples" / "expected_output"


@pytest.fixture(scope="session")
def invoice_txt() -> Path:
    return FIXTURES / "invoice_sample.txt"


@pytest.fixture(scope="session")
def delivery_note_txt() -> Path:
    return FIXTURES / "delivery_note_sample.txt"

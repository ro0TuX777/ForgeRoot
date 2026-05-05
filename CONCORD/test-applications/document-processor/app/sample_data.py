from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SAMPLE_DOCS_DIR = BASE_DIR / "data" / "sample_docs"


def create_sample_documents() -> None:
    SAMPLE_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    sample_pdf = SAMPLE_DOCS_DIR / "sample_document.txt"
    if not sample_pdf.exists():
        sample_pdf.write_text(
            "Page 1:\nHello world.\nPage 2:\nThis is a sample document for CONCORD testing.\n"
        )

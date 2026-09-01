from pathlib import Path

import pymupdf as fitz
import pytest


@pytest.fixture
def make_pdf():
    def create(path: Path, paragraphs: list[str] | None = None, pages: int = 1) -> Path:
        paragraphs = paragraphs or [
            "Chapter One",
            "Elizabeth waited beside the window while the rain crossed the garden.",
            "Mr. Bennet closed the book and listened to the quiet house.",
        ]
        document = fitz.open()
        for page_index in range(pages):
            page = document.new_page(width=595, height=842)
            y = 72
            for paragraph in paragraphs:
                rect = fitz.Rect(72, y, 523, y + 90)
                page.insert_textbox(rect, paragraph, fontname="helv", fontsize=11)
                y += 110
        document.save(path)
        document.close()
        return path

    return create

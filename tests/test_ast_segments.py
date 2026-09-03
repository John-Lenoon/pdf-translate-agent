import pymupdf as fitz
import pytest

from translator.ast import PDFValidationError, parse_pdf
from translator.models import Block, DocumentAST, Page
from translator.segments import split_segments


def test_parse_pdf_keeps_text_coordinates_and_stable_ids(tmp_path, make_pdf):
    source = make_pdf(tmp_path / "book.pdf")
    ast = parse_pdf(source)
    first = split_segments(ast)
    second = split_segments(ast)

    assert ast.page_count == 1
    assert ast.pages[0].blocks[0].bbox != (0, 0, 0, 0)
    assert [item.id for item in first] == [item.id for item in second]
    assert all(item.bbox_refs for item in first)


def test_cross_page_paragraphs_are_joined():
    ast = DocumentAST(
        source_sha256="hash",
        page_count=2,
        pages=[
            Page(number=1, width=100, height=100, blocks=[Block(block_id="b1", text="She crossed the", bbox=(1, 1, 90, 30))]),
            Page(number=2, width=100, height=100, blocks=[Block(block_id="b2", text="silent river at dawn.", bbox=(1, 1, 90, 30))]),
        ],
    )

    segments = split_segments(ast)
    assert len(segments) == 1
    assert segments[0].source_text == "She crossed the silent river at dawn."
    assert len(segments[0].bbox_refs) == 2


def test_parse_pdf_rejects_a_page_with_only_footer_text(tmp_path):
    source = tmp_path / "scanned.pdf"
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((72, 810), "Page 1", fontname="helv", fontsize=9)
    document.save(source)
    document.close()

    with pytest.raises(PDFValidationError, match="PDF_TEXT_COVERAGE_TOO_LOW_PAGE_1"):
        parse_pdf(source)


def test_parse_pdf_accepts_a_short_text_title(tmp_path, make_pdf):
    ast = parse_pdf(make_pdf(tmp_path / "title.pdf", paragraphs=["THE QUIET HOUR"]))

    assert ast.pages[0].blocks[0].text == "THE QUIET HOUR"

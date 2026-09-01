from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pymupdf as fitz

from .models import Block, DocumentAST, Line, Page, Span


class PDFValidationError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_pdf(path: Path) -> DocumentAST:
    source_hash = sha256_file(path)
    try:
        pdf = fitz.open(path)
    except Exception as exc:
        raise PDFValidationError("PDF_OPEN_FAILED") from exc

    try:
        if pdf.needs_pass:
            raise PDFValidationError("PDF_PASSWORD_PROTECTED")
        if pdf.page_count == 0:
            raise PDFValidationError("PDF_HAS_NO_PAGES")
        if pdf.page_count > 50:
            raise PDFValidationError("PDF_EXCEEDS_V1_PAGE_LIMIT")

        pages: list[Page] = []
        extracted_characters = 0
        for page_index, page in enumerate(pdf):
            data = page.get_text("dict")
            blocks: list[Block] = []
            for block_index, raw_block in enumerate(data.get("blocks", [])):
                block_id = f"p{page_index + 1}-b{block_index + 1}"
                bbox = tuple(raw_block.get("bbox", (0, 0, 0, 0)))
                if raw_block.get("type") == 1:
                    blocks.append(Block(block_id=block_id, text="", bbox=bbox, kind="image"))
                    continue
                if raw_block.get("type") != 0:
                    blocks.append(Block(block_id=block_id, text="", bbox=bbox, kind="other"))
                    continue

                lines: list[Line] = []
                for raw_line in raw_block.get("lines", []):
                    spans = [
                        Span(
                            text=span.get("text", ""),
                            bbox=tuple(span["bbox"]),
                            font=span.get("font", ""),
                            size=span.get("size", 0),
                            flags=span.get("flags", 0),
                        )
                        for span in raw_line.get("spans", [])
                        if span.get("text")
                    ]
                    text = "".join(span.text for span in spans).strip()
                    if text:
                        lines.append(Line(text=text, bbox=tuple(raw_line["bbox"]), spans=spans))
                text = "\n".join(line.text for line in lines).strip()
                if text:
                    extracted_characters += len(text)
                    blocks.append(Block(block_id=block_id, text=text, bbox=bbox, lines=lines))
            pages.append(
                Page(
                    number=page_index + 1,
                    width=page.rect.width,
                    height=page.rect.height,
                    blocks=blocks,
                )
            )

            page_characters = sum(
                len(block.text.strip()) for block in blocks if block.kind == "text"
            )
            image_area = sum(
                fitz.Rect(block.bbox).get_area() for block in blocks if block.kind == "image"
            )
            if page_characters < 20 or (
                image_area / max(1, page.rect.get_area()) > 0.5 and page_characters < 200
            ):
                raise PDFValidationError(
                    f"PDF_TEXT_COVERAGE_TOO_LOW_PAGE_{page_index + 1}"
                )

        if extracted_characters < max(20, pdf.page_count * 5):
            raise PDFValidationError("PDF_TEXT_COVERAGE_TOO_LOW")
        metadata = {key: value for key, value in pdf.metadata.items() if value is not None}
        return DocumentAST(
            source_sha256=source_hash,
            page_count=len(pages),
            pages=pages,
            source_metadata=metadata,
        )
    finally:
        pdf.close()


def write_ast(ast: DocumentAST, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(ast.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def read_ast(path: Path) -> DocumentAST:
    return DocumentAST.model_validate_json(path.read_text(encoding="utf-8"))

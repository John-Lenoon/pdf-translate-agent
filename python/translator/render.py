from __future__ import annotations

import json
from pathlib import Path

import pymupdf as fitz

from .ast import sha256_file
from .models import DocumentAST, RenderIssue, RenderReport, Segment


class RenderValidationError(RuntimeError):
    def __init__(self, issue: RenderIssue, report: RenderReport):
        super().__init__(issue.message)
        self.issue = issue
        self.report = report


def _fail(report: RenderReport, issue: RenderIssue) -> None:
    report.issues.append(issue)
    raise RenderValidationError(issue, report)


def _split_translation(text: str, refs) -> list[str]:
    if len(refs) <= 1:
        return [text]
    areas = [max(1, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) for _, bbox in refs]
    total = sum(areas)
    cuts: list[str] = []
    cursor = 0
    for index, area in enumerate(areas):
        if index == len(areas) - 1:
            cuts.append(text[cursor:])
            break
        next_cursor = min(len(text), cursor + round(len(text) * area / total))
        cuts.append(text[cursor:next_cursor])
        cursor = next_cursor
    return cuts


def _normalized_text(text: str) -> str:
    return "".join(text.split())


def _check_collisions(ast: DocumentAST, segments: list[Segment], report: RenderReport) -> None:
    images = {
        page.number: [
            fitz.Rect(block.bbox) for block in page.blocks if block.kind in {"image", "other"}
        ]
        for page in ast.pages
    }
    occupied: dict[int, list[tuple[str, fitz.Rect]]] = {}
    for segment in segments:
        for page_number, bbox in segment.bbox_refs:
            rect = fitz.Rect(bbox)
            for image in images.get(page_number, []):
                if rect.intersects(image) and (rect & image).get_area() > 1:
                    _fail(
                        report,
                        RenderIssue(
                            error_code="collision",
                            message="Translation region collides with an image",
                            page_number=page_number,
                            segment_id=segment.id,
                        ),
                    )
            for other_id, other in occupied.setdefault(page_number, []):
                if other_id != segment.id and rect.intersects(other) and (rect & other).get_area() > 1:
                    _fail(
                        report,
                        RenderIssue(
                            error_code="collision",
                            message=f"Translation regions overlap: {other_id} and {segment.id}",
                            page_number=page_number,
                            segment_id=segment.id,
                        ),
                    )
            occupied[page_number].append((segment.id, rect))


def render_overlay(
    source_pdf: Path,
    output_pdf: Path,
    translations: dict[str, str],
    segments: list[Segment],
    ast: DocumentAST,
    *,
    font_path: Path | None = None,
    minimum_font_size: float = 4,
) -> RenderReport:
    source_hash = sha256_file(source_pdf)
    report = RenderReport(source_sha256=source_hash, page_count=ast.page_count)
    if source_hash != ast.source_sha256:
        _fail(
            report,
            RenderIssue(error_code="source_modified", message="Source PDF changed after parsing"),
        )

    _check_collisions(ast, segments, report)
    temp_pdf = output_pdf.with_suffix(".tmp.pdf")
    temp_pdf.unlink(missing_ok=True)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(source_pdf)
    font_name = "translation-font" if font_path else "china-s"
    try:
        if doc.page_count != ast.page_count:
            _fail(
                report,
                RenderIssue(error_code="unreadable_page", message="Source page count changed"),
            )

        font = fitz.Font(fontfile=str(font_path)) if font_path else fitz.Font(fontname=font_name)
        rendered_ids: set[str] = set()
        expected_fragments: dict[int, list[tuple[str, str]]] = {}
        for segment in segments:
            translation = translations.get(segment.id)
            if not translation:
                _fail(
                    report,
                    RenderIssue(
                        error_code="overflow",
                        message="A segment has no translation",
                        page_number=segment.page_number,
                        segment_id=segment.id,
                    ),
                )
            missing = sorted({character for character in translation if not character.isspace() and not font.has_glyph(ord(character))})
            if missing:
                _fail(
                    report,
                    RenderIssue(
                        error_code="missing_glyph",
                        message=f"Font is missing glyphs: {''.join(missing[:8])}",
                        page_number=segment.page_number,
                        segment_id=segment.id,
                    ),
                )

            fragments = _split_translation(translation, segment.bbox_refs)
            for (page_number, bbox), fragment in zip(segment.bbox_refs, fragments, strict=True):
                page = doc[page_number - 1]
                rect = fitz.Rect(bbox)
                if rect.is_empty or not page.rect.contains(rect):
                    _fail(
                        report,
                        RenderIssue(
                            error_code="overflow",
                            message="Translation rectangle is outside the page",
                            page_number=page_number,
                            segment_id=segment.id,
                        ),
                    )
                if font_path:
                    page.insert_font(fontname=font_name, fontfile=str(font_path))
                page.draw_rect(rect, color=None, fill=(1, 1, 1), overlay=True)
                base_size = max(minimum_font_size, min(12.0, rect.height * 0.45))
                remaining = -1.0
                font_size = base_size
                # Keep PyMuPDF's normal line metrics; values below 1 can report
                # false overflow for CJK glyphs even when the line visibly fits.
                lineheight = 1.0 if "\n" not in fragment and len(fragment) <= 80 else 1.15
                while font_size >= minimum_font_size:
                    shape = page.new_shape()
                    remaining = shape.insert_textbox(
                        rect,
                        fragment,
                        fontname=font_name,
                        fontsize=font_size,
                        lineheight=lineheight,
                        color=(0, 0, 0),
                    )
                    if remaining >= 0:
                        shape.commit(overlay=True)
                        break
                    font_size -= 0.5
                # PyMuPDF's textbox layout can reject a short CJK line because
                # of conservative ascender/descender metrics. For single-line
                # fragments, use a baseline insertion only after independently
                # proving that the measured glyph run fits the original box.
                if remaining < 0 and "\n" not in fragment and fragment.strip():
                    candidate = max(minimum_font_size, font_size + 0.5)
                    width = font.text_length(fragment, fontsize=candidate)
                    height = candidate * 1.2
                    if width <= rect.width + 0.01 and height <= rect.height + 0.01:
                        page.insert_text(
                            (rect.x0, rect.y0 + candidate),
                            fragment,
                            fontname=font_name,
                            fontsize=candidate,
                            color=(0, 0, 0),
                            overlay=True,
                        )
                        remaining = 0.0
                if remaining < 0:
                    _fail(
                        report,
                        RenderIssue(
                            error_code="overflow",
                            message="Translation does not fit at the minimum font size",
                            page_number=page_number,
                            segment_id=segment.id,
                        ),
                    )
                if fragment.strip():
                    expected_fragments.setdefault(page_number, []).append((segment.id, fragment))
            rendered_ids.add(segment.id)

        report.rendered_segments = len(rendered_ids)
        doc.save(temp_pdf, garbage=4, deflate=True)
    finally:
        doc.close()

    if sha256_file(source_pdf) != source_hash:
        temp_pdf.unlink(missing_ok=True)
        _fail(
            report,
            RenderIssue(error_code="source_modified", message="Source PDF was modified during rendering"),
        )

    try:
        verification = fitz.open(temp_pdf)
        try:
            if verification.page_count != ast.page_count:
                _fail(
                    report,
                    RenderIssue(error_code="unreadable_page", message="Output page count mismatch"),
                )
            for page_number, page in enumerate(verification, start=1):
                extracted = page.get_text("text")
                if not extracted.strip():
                    _fail(
                        report,
                        RenderIssue(
                            error_code="unreadable_page",
                            message="Rendered page has no extractable text",
                            page_number=page_number,
                        ),
                    )
                normalized_page = _normalized_text(extracted)
                for segment_id, fragment in expected_fragments.get(page_number, []):
                    if _normalized_text(fragment) not in normalized_page:
                        _fail(
                            report,
                            RenderIssue(
                                error_code="unreadable_page",
                                message="Rendered translation text is incomplete or unreadable",
                                page_number=page_number,
                                segment_id=segment_id,
                            ),
                        )
        finally:
            verification.close()
        report.output_sha256 = sha256_file(temp_pdf)
        temp_pdf.replace(output_pdf)
        output_pdf.with_suffix(".report.json").write_text(
            json.dumps(report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return report
    except Exception:
        temp_pdf.unlink(missing_ok=True)
        raise

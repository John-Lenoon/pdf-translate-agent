from __future__ import annotations

import html
import json
import os
import base64
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

import pymupdf as fitz

from .models import DocumentAST, Segment


@dataclass(frozen=True)
class ReflowBlock:
    segment_id: str | None
    source_page: int
    source_text: str
    translation: str
    kind: Literal["heading", "paragraph", "image"]
    level: int = 1
    image_data_uri: str | None = None
    source_block_id: str | None = None
    source_bbox: tuple[float, float, float, float] | None = None
    structure_decision: dict[str, Any] | None = None


@dataclass(frozen=True)
class ReflowChapter:
    chapter_id: str
    blocks: tuple[ReflowBlock, ...]


@dataclass(frozen=True)
class ReflowDocument:
    version: str
    source_page_count: int
    chapters: tuple[ReflowChapter, ...]

    def artifact(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "source_page_count": self.source_page_count,
            "chapters": [
                {
                    "id": chapter.chapter_id,
                    "blocks": [
                        {
                            "kind": block.kind,
                            "segment_id": block.segment_id,
                            "source_page": block.source_page,
                            "source_block_id": block.source_block_id,
                            "source_bbox": block.source_bbox,
                            "structure": {
                                "level": block.level,
                                "decision": block.structure_decision,
                            },
                        }
                        for block in chapter.blocks
                    ],
                }
                for chapter in self.chapters
            ],
        }


class StructureReviewer(Protocol):
    def classify_reflow_structure(self, source: str, hints: dict) -> Any: ...


def classify_block(segment: Segment, reviewer: StructureReviewer | None = None) -> tuple[str, int, dict[str, Any] | None]:
    text = segment.source_text.strip()
    words = text.split()
    lower = text.casefold()
    if lower.startswith(("chapter ", "book ", "part ")) and len(words) <= 12:
        return "heading", 1, {"confidence": 1.0, "reason": "chapter keyword"}
    if len(text) <= 90 and text.isupper() and len(words) <= 12:
        return "heading", 2, {"confidence": 0.9, "reason": "short uppercase block"}
    if reviewer and len(text) <= 180:
        try:
            result = reviewer.classify_reflow_structure(
                text,
                {"word_count": len(words), "source_page": segment.page_number},
            )
            if result.confidence >= 0.75:
                return result.block_type, result.level, {
                    "confidence": result.confidence,
                    "reason": result.reason,
                }
            return "paragraph", 0, {"confidence": result.confidence, "reason": "structure_uncertain"}
        except Exception:
            return "paragraph", 0, {"confidence": 0.0, "reason": "structure_uncertain"}
    return "paragraph", 0, None


def _cluster_drawing_regions(page: fitz.Page) -> list[fitz.Rect]:
    """Coalesce touching vector paths so a map becomes one source-region image."""
    regions = [
        fitz.Rect(item["rect"])
        for item in page.get_drawings()
        if fitz.Rect(item["rect"]).get_area() >= 144
    ]
    clusters: list[fitz.Rect] = []
    for region in sorted(regions, key=lambda rect: (rect.y0, rect.x0)):
        expanded = fitz.Rect(region.x0 - 6, region.y0 - 6, region.x1 + 6, region.y1 + 6)
        for index, cluster in enumerate(clusters):
            if expanded.intersects(cluster):
                clusters[index] = cluster | region
                break
        else:
            clusters.append(region)
    return [region for region in clusters if region.get_area() >= 900]


def extract_reflow_images(source_pdf: Path, ast: DocumentAST, asset_dir: Path) -> dict[int, list[ReflowBlock]]:
    """Extract image blocks, falling back to a clipped page image for vector-only artwork."""
    asset_dir.mkdir(parents=True, exist_ok=True)
    images: dict[int, list[ReflowBlock]] = {}
    document = fitz.open(source_pdf)
    try:
        for page_model in ast.pages:
            page = document[page_model.number - 1]
            candidates = [
                (block.block_id, fitz.Rect(block.bbox))
                for block in page_model.blocks
                if block.kind == "image"
                and (block.bbox[2] - block.bbox[0]) * (block.bbox[3] - block.bbox[1]) >= 900
            ]
            for index, drawing in enumerate(_cluster_drawing_regions(page), start=1):
                if not any((drawing & image).get_area() >= 0.8 * min(drawing.get_area(), image.get_area()) for _, image in candidates):
                    candidates.append((f"p{page_model.number}-drawing-{index}", drawing))
            for index, (block_id, clip) in enumerate(sorted(candidates, key=lambda item: (item[1].y0, item[1].x0)), start=1):
                if clip.is_empty:
                    continue
                pixmap = page.get_pixmap(clip=clip, matrix=fitz.Matrix(2, 2), alpha=False)
                target = asset_dir / f"p{page_model.number:04d}-{index:02d}.png"
                pixmap.save(target)
                encoded = base64.b64encode(target.read_bytes()).decode("ascii")
                images.setdefault(page_model.number, []).append(
                    ReflowBlock(
                        segment_id=None,
                        source_page=page_model.number,
                        source_text="",
                        translation="",
                        kind="image",
                        image_data_uri=f"data:image/png;base64,{encoded}",
                        source_block_id=block_id,
                        source_bbox=(clip.x0, clip.y0, clip.x1, clip.y1),
                    )
                )
    finally:
        document.close()
    return images


def build_reflow_chapters(
    ast: DocumentAST,
    segments: list[Segment],
    translations: dict[str, str],
    *,
    images: dict[int, list[ReflowBlock]] | None = None,
    reviewer: StructureReviewer | None = None,
) -> ReflowDocument:
    grouped: dict[str, list[ReflowBlock]] = {}
    order: list[str] = []
    inserted_images: set[str] = set()
    for segment in segments:
        chapter_id = segment.chapter_id or "chapter-0001"
        if chapter_id not in grouped:
            grouped[chapter_id] = []
            order.append(chapter_id)
        if images:
            segment_top = min((bbox[1] for page, bbox in segment.bbox_refs if page == segment.page_number), default=0)
            for image in images.get(segment.page_number, []):
                image_key = image.source_block_id or f"page-{image.source_page}"
                if image_key not in inserted_images and (image.source_bbox is None or image.source_bbox[1] <= segment_top):
                    grouped[chapter_id].append(image)
                    inserted_images.add(image_key)
        kind, level, decision = classify_block(segment, reviewer)
        grouped[chapter_id].append(
            ReflowBlock(
                segment_id=segment.id,
                source_page=segment.page_number,
                source_text=segment.source_text,
                translation=translations.get(segment.id, "").strip(),
                kind=kind,
                level=level,
                structure_decision=decision,
            )
        )
    # A graphic below the final text block (or on an image-only page) still belongs
    # in the reading edition. Attach it to the last available chapter.
    if images and order:
        fallback = grouped[order[-1]]
        for page_images in images.values():
            for image in page_images:
                image_key = image.source_block_id or f"page-{image.source_page}"
                if image_key not in inserted_images:
                    fallback.append(image)
                    inserted_images.add(image_key)
    return ReflowDocument("reflow-v1", ast.page_count, tuple(ReflowChapter(chapter_id, tuple(grouped[chapter_id])) for chapter_id in order))


def _block_html(block: ReflowBlock) -> str:
    if block.kind == "image":
        return f'<figure data-source-page="{block.source_page}" data-source-block="{html.escape(block.source_block_id or "", quote=True)}"><img src="{block.image_data_uri}" alt="Source illustration from page {block.source_page}"></figure>'
    text = html.escape(block.translation)
    source = html.escape(block.source_text, quote=True)
    attrs = f'data-source-page="{block.source_page}" data-source-segment="{html.escape(block.segment_id, quote=True)}" title="{source}"'
    if block.kind == "heading":
        tag = "h1" if block.level == 1 else "h2"
        return f'<{tag} {attrs}>{text}</{tag}>'
    return f'<p {attrs}>{text}</p>'


def render_html(
    document: ReflowDocument,
    *,
    page_width_pt: float,
    page_height_pt: float,
    font_family: str = "Noto Serif CJK SC, Source Han Serif SC, SimSun, serif",
    font_path: Path | None = None,
    repair_pass: int = 0,
) -> str:
    font_face = ""
    if font_path:
        if not font_path.is_file():
            raise ReflowRenderError(f"Configured font does not exist: {font_path}")
        encoded = base64.b64encode(font_path.read_bytes()).decode("ascii")
        font_face = f"@font-face {{ font-family: 'ConfiguredTranslationFont'; src: url(data:font/ttf;base64,{encoded}) format('truetype'); }}"
        font_family = "ConfiguredTranslationFont, " + font_family
    chapter_html = []
    for index, chapter in enumerate(document.chapters):
        blocks = "\n".join(_block_html(block) for block in chapter.blocks)
        class_name = "chapter" if index else "chapter first-chapter"
        chapter_html.append(f'<section class="{class_name}" data-chapter="{html.escape(chapter.chapter_id)}">{blocks}</section>')
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><style>{font_face}
@page {{ size: {page_width_pt:g}pt {page_height_pt:g}pt; margin: {max(54, 72 - repair_pass * 6)}pt 68pt 64pt; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
body {{ color: #171717; font-family: {font_family}; font-size: 13pt; line-height: {max(1.55, 1.75 - repair_pass * 0.08):g}; text-rendering: optimizeLegibility; }}
.chapter {{ break-before: page; }}
.first-chapter {{ break-before: auto; }}
h1, h2 {{ break-after: avoid; page-break-after: avoid; font-weight: 700; line-height: 1.35; margin: 0 0 30pt; }}
h1 {{ font-size: 24pt; text-align: left; }}
h2 {{ font-size: 17pt; margin-top: 24pt; }}
p {{ margin: 0 0 14pt; text-indent: 2em; orphans: 2; widows: 2; }}
h1 + p, h2 + p {{ text-indent: 2em; }}
figure {{ break-inside: avoid; margin: 18pt auto; text-align: center; }}
figure img {{ display: inline-block; max-width: 100%; max-height: {page_height_pt * 0.62:g}pt; object-fit: contain; }}
</style></head><body>{''.join(chapter_html)}</body></html>'''


class ReflowRenderError(RuntimeError):
    pass


def inspect_reflow_pdf(output_pdf: Path, document: ReflowDocument, screenshot_dir: Path) -> dict[str, Any]:
    """Hard PDF checks plus deterministic visual metrics for model-review routing."""
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    pdf = fitz.open(output_pdf)
    try:
        if pdf.page_count == 0:
            raise ReflowRenderError("Reflow PDF has no pages")
        expected = [block for chapter in document.chapters for block in chapter.blocks if block.segment_id]
        normalized_text = "".join("".join(page.get_text("text").split()) for page in pdf)
        missing = [block.segment_id for block in expected if "".join(block.translation.split()) not in normalized_text]
        if missing:
            raise ReflowRenderError(f"Reflow PDF is missing translated segments: {', '.join(missing[:3])}")

        output_pages: dict[str, int] = {}
        metrics: list[dict[str, Any]] = []
        hard_issues: list[dict[str, Any]] = []
        for number, page in enumerate(pdf, start=1):
            text_dict = page.get_text("dict")
            spans = [span for block in text_dict["blocks"] if block.get("type") == 0 for line in block.get("lines", []) for span in line.get("spans", []) if span.get("text", "").strip()]
            if not spans:
                hard_issues.append({"type": "blank_page", "page": number})
                continue
            body_spans = [span for span in spans if span["bbox"][1] < page.rect.height - 48]
            min_font = min(span["size"] for span in body_spans or spans)
            if min_font < 11.5:
                hard_issues.append({"type": "body_font_below_floor", "page": number, "font_size": min_font})
            # Global page numbers live in the footer. They are intentionally added
            # after merging chapters and must not participate in body collision checks.
            rects = [
                fitz.Rect(block["bbox"])
                for block in text_dict["blocks"]
                if block.get("type") == 0
                and block.get("lines")
                and block["bbox"][1] < page.rect.height - 48
            ]
            overlap_count = sum(
                1
                for index, rect in enumerate(rects)
                for other in rects[index + 1:]
                if rect.intersects(other)
                and (rect & other).get_area() > 8
                and (rect & other).get_area() >= 0.8 * min(rect.get_area(), other.get_area())
            )
            if overlap_count:
                hard_issues.append({"type": "text_overlap", "page": number, "count": overlap_count})
            pixmap = page.get_pixmap(matrix=fitz.Matrix(0.35, 0.35), colorspace=fitz.csGRAY, alpha=False)
            image_path = screenshot_dir / f"page-{number:04d}.png"
            pixmap.save(image_path)
            ink = sum(1 for value in pixmap.samples if value < 245) / max(1, len(pixmap.samples))
            metrics.append(
                {
                    "page": number,
                    "page_width_pt": round(page.rect.width, 2),
                    "page_height_pt": round(page.rect.height, 2),
                    "min_font_size": round(min_font, 2),
                    "ink_ratio": round(ink, 4),
                    "text_spans": len(spans),
                    "body_text_blocks": len(rects),
                    "embedded_images": len(page.get_images(full=True)),
                    "screenshot": str(image_path.name),
                    "suspicious": ink < 0.015 or ink > 0.62,
                }
            )
            page_text = "".join(page.get_text("text").split())
            for block in expected:
                if block.segment_id not in output_pages and "".join(block.translation.split()) in page_text:
                    output_pages[block.segment_id] = number
        if hard_issues:
            raise ReflowRenderError(f"Reflow hard validation failed: {hard_issues[0]['type']}")
        return {"output_page_count": pdf.page_count, "metrics": metrics, "output_pages": output_pages, "hard_issues": hard_issues}
    finally:
        pdf.close()


def render_reflow_pdf(
    html_text: str,
    output_pdf: Path,
    *,
    page_width_pt: float,
    page_height_pt: float,
    script_path: Path | None = None,
    page_numbers: bool = True,
) -> None:
    script = script_path or Path(__file__).resolve().parents[2] / "scripts" / "reflow-render.mjs"
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    payload = {"html": html_text, "output": str(output_pdf.resolve()), "width": page_width_pt, "height": page_height_pt, "page_numbers": page_numbers}
    try:
        completed = subprocess.run(
            ["node", str(script)],
            # ASCII JSON avoids Windows console-codepage corruption of paths containing CJK.
            input=json.dumps(payload, ensure_ascii=True),
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "NODE_NO_WARNINGS": "1"},
        )
    except OSError as exc:
        raise ReflowRenderError("Node.js is required for reflow PDF rendering") from exc
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise ReflowRenderError(detail or "Chromium reflow rendering failed")


def merge_chapter_pdfs(chapter_paths: list[Path], output_pdf: Path) -> None:
    merged = fitz.open()
    try:
        for path in chapter_paths:
            chapter = fitz.open(path)
            try:
                merged.insert_pdf(chapter)
            finally:
                chapter.close()
        if merged.page_count == 0:
            raise ReflowRenderError("No chapter pages were generated")
        for number, page in enumerate(merged, start=1):
            page.insert_text(
                (page.rect.width / 2 - 6, page.rect.height - 32),
                str(number),
                fontname="china-s",
                fontsize=9,
                color=(0.45, 0.45, 0.45),
                overlay=True,
            )
        merged.save(output_pdf, garbage=4, deflate=True)
    finally:
        merged.close()

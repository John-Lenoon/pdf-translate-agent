from __future__ import annotations

import hashlib
import re

from .models import DocumentAST, Segment


CHAPTER_RE = re.compile(r"^(chapter|book|part)\s+([\divxlcdm]+|[a-z]+)\b", re.IGNORECASE)
SENTENCE_END_RE = re.compile(r"[.!?\"'\u2019\u201d)]$")


def _stable_id(source_hash: str, page: int, ordinal: int, text: str) -> str:
    digest = hashlib.sha256(f"{source_hash}:{text}".encode("utf-8")).hexdigest()[:12]
    return f"p{page:04d}-s{ordinal:04d}-{digest}"


def _can_merge_across_page(previous: Segment, current_text: str, current_page: int) -> bool:
    return (
        current_page == previous.page_number + 1
        and not SENTENCE_END_RE.search(previous.source_text.rstrip())
        and bool(current_text)
        and current_text[0].islower()
    )


def split_segments(ast: DocumentAST) -> list[Segment]:
    segments: list[Segment] = []
    ordinal = 0
    chapter_number = 0
    for page in ast.pages:
        for block in page.blocks:
            if block.kind != "text" or not block.text.strip():
                continue
            paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", block.text) if paragraph.strip()]
            for paragraph in paragraphs:
                if CHAPTER_RE.match(paragraph):
                    chapter_number += 1
                chapter_id = f"chapter-{max(chapter_number, 1):04d}"
                if segments and _can_merge_across_page(segments[-1], paragraph, page.number):
                    previous = segments[-1]
                    previous.source_text = f"{previous.source_text} {paragraph}"
                    previous.bbox_refs.append((page.number, block.bbox))
                    previous.id = _stable_id(ast.source_sha256, previous.page_number, previous.ordinal, previous.source_text)
                    continue
                ordinal += 1
                segments.append(
                    Segment(
                        id=_stable_id(ast.source_sha256, page.number, ordinal, paragraph),
                        page_number=page.number,
                        ordinal=ordinal,
                        chapter_id=chapter_id,
                        source_text=paragraph,
                        bbox_refs=[(page.number, block.bbox)],
                    )
                )
    for index, segment in enumerate(segments):
        segment.context_before = [item.source_text for item in segments[max(0, index - 2):index]]
        segment.context_after = [item.source_text for item in segments[index + 1:index + 3]]
    return segments

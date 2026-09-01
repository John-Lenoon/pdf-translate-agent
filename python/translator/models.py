from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class Span(BaseModel):
    text: str
    bbox: tuple[float, float, float, float]
    font: str = ""
    size: float = 0
    flags: int = 0


class Line(BaseModel):
    text: str
    bbox: tuple[float, float, float, float]
    spans: list[Span] = Field(default_factory=list)


class Block(BaseModel):
    block_id: str
    text: str
    bbox: tuple[float, float, float, float]
    lines: list[Line] = Field(default_factory=list)
    kind: Literal["text", "image", "other"] = "text"


class Page(BaseModel):
    number: int
    width: float
    height: float
    blocks: list[Block] = Field(default_factory=list)


class DocumentAST(BaseModel):
    ast_version: str = "1"
    source_sha256: str
    page_count: int
    pages: list[Page]
    source_metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class Segment(BaseModel):
    id: str
    page_number: int
    ordinal: int
    chapter_id: str | None = None
    source_text: str
    bbox_refs: list[tuple[int, tuple[float, float, float, float]]] = Field(default_factory=list)
    context_before: list[str] = Field(default_factory=list)
    context_after: list[str] = Field(default_factory=list)


class EntityObservation(BaseModel):
    source_name: str
    target_name: str
    entity_type: Literal["person"] = "person"
    evidence_text: str = ""


class TranslationResult(BaseModel):
    translation: str
    entity_observations: list[EntityObservation] = Field(default_factory=list)
    glossary_suggestions: list[dict[str, str]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ChapterSummaryResult(BaseModel):
    summary: str


class RenderIssue(BaseModel):
    error_code: Literal["missing_glyph", "overflow", "collision", "unreadable_page", "source_modified"]
    message: str
    page_number: int | None = None
    segment_id: str | None = None


class RenderReport(BaseModel):
    source_sha256: str
    output_sha256: str | None = None
    page_count: int
    rendered_segments: int = 0
    issues: list[RenderIssue] = Field(default_factory=list)

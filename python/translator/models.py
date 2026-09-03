from __future__ import annotations

from typing import Any, Literal
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


class EntityDiscoveryResult(BaseModel):
    entities: list[EntityObservation] = Field(default_factory=list)


class TranslationResult(BaseModel):
    translation: str
    entity_observations: list[EntityObservation] = Field(default_factory=list)
    glossary_suggestions: list[dict[str, str]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    risk_label: Literal["low", "medium", "high"] = "low"


class ChapterSummaryResult(BaseModel):
    summary: str


class StructureReviewResult(BaseModel):
    block_type: Literal["heading", "paragraph"]
    level: int = Field(default=0, ge=0, le=3)
    confidence: float = Field(ge=0, le=1)
    reason: str = ""


class FormatReviewResult(BaseModel):
    status: Literal["pass", "fail"]
    issues: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


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


class RunModelPlan(BaseModel):
    plan_version: str = "v2.1"
    local_adapter: Literal["ollama"] = "ollama"
    local_endpoint: str
    local_model: str
    local_context_window: int = Field(gt=0)
    local_max_output_tokens: int = Field(gt=0)
    local_batch_concurrency: int = Field(default=1, ge=1)
    remote_adapter: Literal["openai_compatible"] | None = None
    remote_endpoint: str | None = None
    remote_model: str | None = None
    credential_vault_ref: str | None = None
    remote_max_concurrency: int = Field(default=1, ge=1)
    prompt_version: str
    workflow_version: str
    risk_policy_version: str


class TranslationCandidate(BaseModel):
    source: Literal["local", "remote"]
    text: str = Field(min_length=1)
    model: str
    prompt_version: str
    context_version: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RoutingDecision(BaseModel):
    score: float = Field(ge=0, le=1)
    signals: list[str] = Field(default_factory=list)
    risk_label: Literal["low", "medium", "high"] = "low"
    route: Literal["local_only", "remote_review"]
    review_status: Literal["not_required", "kept", "revised", "review_debt", "failed"]
    selection_reason: str

import base64
import json
from pathlib import Path

import pytest

from translator.ast import sha256_file
from translator.coordinator import TranslationCoordinator
from translator.db import Database
from translator.models import EntityObservation, FormatReviewResult, StructureReviewResult, TranslationResult
from translator.render import RenderValidationError, render_overlay
from translator.reflow import build_reflow_chapters, classify_block, extract_reflow_images, render_html
from translator.routing import QualityRouter
from translator.workflow import Workflow, WorkflowError
from translator.ast import parse_pdf
from translator.segments import split_segments


class FakeProvider:
    model = "fake-model"
    last_metadata = {"response_id": "fake"}

    def __init__(self):
        self.calls: list[str] = []
        self.summary_calls = 0

    def summarize_chapter(self, chapter_text: str) -> str:
        self.summary_calls += 1
        return "章节摘要"

    def translate(self, source, context, entities, glossary):
        self.calls.append(source)
        observations = []
        if "Elizabeth" in source:
            observations.append(
                EntityObservation(
                    source_name="Elizabeth",
                    target_name="伊丽莎白",
                    evidence_text="Elizabeth",
                )
            )
        translation = f"译文{len(self.calls)}"
        if "Elizabeth" in source:
            translation += " 伊丽莎白"
        return TranslationResult(
            translation=translation,
            entity_observations=observations,
            glossary_suggestions=[{"source": "rain", "target": "雨"}],
        )


def setup_workflow(tmp_path: Path, source: Path):
    root = tmp_path / "runs"
    db = Database(root / "state.sqlite3")
    provider = FakeProvider()
    workflow = Workflow(root, db, provider)
    run_id = workflow.create(source, "request-1", [{"source": "house", "target": "宅邸"}])
    return root, db, provider, workflow, run_id


def test_workflow_completes_and_preserves_source(tmp_path, make_pdf):
    source = make_pdf(tmp_path / "book.pdf")
    before = sha256_file(source)
    root, db, provider, workflow, run_id = setup_workflow(tmp_path, source)

    workflow.execute(run_id)

    assert db.run(run_id)["status"] == "completed"
    assert sha256_file(source) == before
    assert (root / run_id / "translated.pdf").is_file()
    assert (root / run_id / "translated.report.json").is_file()
    assert provider.calls
    assert all(row["status"] == "translated" for row in db.segments(run_id))


def test_workflow_reflow_mode_generates_readable_pdf(tmp_path, make_pdf, monkeypatch):
    monkeypatch.setenv("V2_RENDER_MODE", "reflow")
    source = make_pdf(tmp_path / "reflow-book.pdf", paragraphs=["Chapter Three: The Map", "A short paragraph for the reading edition."])
    import pymupdf as fitz
    pdf = fitz.open(source)
    try:
        pdf[0].insert_image(
            fitz.Rect(72, 220, 172, 320),
            stream=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="),
        )
        pdf.save(tmp_path / "reflow-book-with-image.pdf")
    finally:
        pdf.close()
    source = tmp_path / "reflow-book-with-image.pdf"
    root, db, provider, workflow, run_id = setup_workflow(tmp_path, source)

    workflow.execute(run_id)

    output = root / run_id / "translated.pdf"
    assert db.run(run_id)["status"] == "completed"
    assert output.is_file()
    assert list((root / run_id / "reflow-assets").glob("*.png"))
    import pymupdf as fitz
    document = fitz.open(output)
    try:
        assert document.page_count >= 1
        assert "译文" in "".join(page.get_text() for page in document)
    finally:
        document.close()


def test_resume_skips_valid_translations(tmp_path, make_pdf):
    source = make_pdf(tmp_path / "book.pdf")
    root, db, provider, workflow, run_id = setup_workflow(tmp_path, source)
    workflow.execute(run_id)
    calls = len(provider.calls)
    db.set_run(run_id, "failed", "INTERRUPTED", "test interruption")
    (root / run_id / "glossary_suggestions.jsonl").write_text("", encoding="utf-8")

    workflow.execute(run_id)
    assert len(provider.calls) == calls
    assert db.run(run_id)["status"] == "completed"
    suggestions = (root / run_id / "glossary_suggestions.jsonl").read_text(
        encoding="utf-8"
    )
    assert suggestions.count('"source": "rain"') == calls


def test_judge_retranslates_only_selected_segment(tmp_path, make_pdf):
    source = make_pdf(tmp_path / "book.pdf")
    _, db, provider, workflow, run_id = setup_workflow(tmp_path, source)
    workflow.execute(run_id)
    rows = db.segments(run_id)
    selected = rows[1]["id"]
    before = len(provider.calls)
    db.record_judgment(run_id, selected, "coherence", "Use the previous paragraph")

    workflow.execute(run_id)

    assert len(provider.calls) == before + 1
    refreshed = {row["id"]: row for row in db.segments(run_id)}
    assert refreshed[selected]["attempt"] == 2
    assert db.run(run_id)["status"] == "completed"


def test_cancelled_run_stops_before_model_calls(tmp_path, make_pdf):
    source = make_pdf(tmp_path / "book.pdf")
    _, db, provider, workflow, run_id = setup_workflow(tmp_path, source)
    db.request_cancel(run_id)

    workflow.execute(run_id)

    assert db.run(run_id)["status"] == "cancelled"
    assert provider.calls == []


def test_source_change_invalidates_run(tmp_path, make_pdf):
    source = make_pdf(tmp_path / "book.pdf")
    _, db, _provider, workflow, run_id = setup_workflow(tmp_path, source)
    source.write_bytes(source.read_bytes() + b"changed")

    with pytest.raises(WorkflowError, match="changed"):
        workflow.execute(run_id)
    assert db.run(run_id)["error_code"] == "SOURCE_CHANGED"


def test_renderer_rejects_missing_glyph(tmp_path, make_pdf):
    source = make_pdf(tmp_path / "book.pdf")
    ast = parse_pdf(source)
    segments = split_segments(ast)

    with pytest.raises(RenderValidationError) as caught:
        render_overlay(source, tmp_path / "out.pdf", {segment.id: "😀" for segment in segments}, segments, ast)
    assert caught.value.issue.error_code == "missing_glyph"


def test_renderer_rejects_overflow(tmp_path, make_pdf):
    source = make_pdf(tmp_path / "book.pdf")
    ast = parse_pdf(source)
    segments = split_segments(ast)
    segments[0].bbox_refs = [(1, (10, 10, 20, 20))]

    with pytest.raises(RenderValidationError) as caught:
        render_overlay(source, tmp_path / "out.pdf", {segment.id: "很长的译文" * 100 for segment in segments}, segments, ast)
    assert caught.value.issue.error_code == "overflow"


def test_renderer_expands_into_free_space_for_long_translation(tmp_path, make_pdf):
    source = make_pdf(tmp_path / "book.pdf", paragraphs=["A short line", "Another line"])
    ast = parse_pdf(source)
    segments = split_segments(ast)
    segments[0].bbox_refs = [(1, (60, 60, 420, 66))]
    segments[1].bbox_refs = [(1, (60, 180, 420, 186))]

    report = render_overlay(
        source,
        tmp_path / "out.pdf",
        {segments[0].id: "这是一段较长的中文翻译，用于验证渲染器能够向下扩展到页面空白区域。" * 2,
         segments[1].id: "第二段"},
        segments,
        ast,
    )

    assert report.rendered_segments == 2
    assert (tmp_path / "out.pdf").is_file()


def test_renderer_accepts_single_line_cjk_title_when_textbox_metrics_are_conservative(
    tmp_path, make_pdf
):
    source = make_pdf(tmp_path / "book.pdf", paragraphs=["THE QUIET HOUR"])
    ast = parse_pdf(source)
    segments = split_segments(ast)
    segment = segments[0]
    segment.bbox_refs = [(1, (80, 80, 180, 86))]

    report = render_overlay(
        source,
        tmp_path / "out.pdf",
        {segment.id: "静默时光"},
        [segment],
        ast,
    )

    assert report.rendered_segments == 1
    assert (tmp_path / "out.pdf").is_file()


def test_renderer_output_contains_every_translation(tmp_path, make_pdf):
    source = make_pdf(tmp_path / "book.pdf")
    ast = parse_pdf(source)
    segments = split_segments(ast)
    translations = {segment.id: f"第{segment.ordinal}段译文" for segment in segments}

    report = render_overlay(
        source,
        tmp_path / "out.pdf",
        translations,
        segments,
        ast,
    )

    assert report.rendered_segments == len(segments)
    assert report.issues == []


def test_reflow_html_preserves_chapter_structure_and_source_mapping(tmp_path, make_pdf):
    source = make_pdf(tmp_path / "reflow-book.pdf", paragraphs=["Chapter Three: The Map", "He placed the newspaper on the bench."])
    ast = parse_pdf(source)
    segments = split_segments(ast)
    translations = {segments[0].id: "第三章：地图", segments[1].id: "他把报纸放在长椅上。"}
    document = build_reflow_chapters(ast, segments, translations)

    assert classify_block(segments[0])[:2] == ("heading", 1)
    html = render_html(document, page_width_pt=612, page_height_pt=792)
    assert '<h1 data-source-page="1"' in html
    assert "第三章：地图" in html
    assert f'data-source-segment="{segments[1].id}"' in html
    assert ".chapter { break-before: page; }" in html


def test_reflow_records_model_structure_decision(tmp_path, make_pdf):
    class Reviewer:
        def classify_reflow_structure(self, source, hints):
            return StructureReviewResult(
                block_type="heading", level=2, confidence=0.91, reason="short section label"
            )

    source = make_pdf(tmp_path / "structure.pdf", paragraphs=["The following morning"])
    ast = parse_pdf(source)
    segments = split_segments(ast)
    document = build_reflow_chapters(
        ast, segments, {segments[0].id: "次日清晨"}, reviewer=Reviewer()
    )

    block = document.chapters[0].blocks[0]
    assert (block.kind, block.level) == ("heading", 2)
    assert document.artifact()["chapters"][0]["blocks"][0]["structure"]["decision"]["reason"] == "short section label"


def test_reflow_extracts_source_images_for_html(tmp_path, make_pdf):
    import pymupdf as fitz

    source = make_pdf(tmp_path / "illustrated.pdf", paragraphs=["A caption for the illustration."])
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    pdf = fitz.open(source)
    try:
        pdf[0].insert_image(fitz.Rect(72, 180, 172, 280), stream=png)
        pdf[0].draw_rect(fitz.Rect(220, 180, 380, 300), color=(0, 0, 0), fill=(0.8, 0.8, 0.8))
        pdf.save(tmp_path / "illustrated-with-image.pdf")
    finally:
        pdf.close()
    illustrated = tmp_path / "illustrated-with-image.pdf"
    ast = parse_pdf(illustrated)
    images = extract_reflow_images(illustrated, ast, tmp_path / "assets")
    segments = split_segments(ast)
    document = build_reflow_chapters(ast, segments, {segments[0].id: "插图说明。"}, images=images)

    assert list((tmp_path / "assets").glob("*.png"))
    assert len(images[1]) >= 2
    html = render_html(document, page_width_pt=612, page_height_pt=792)
    assert html.count("<figure") >= 2
    assert "data:image/png;base64," in html


def test_reflow_remote_format_failure_repairs_chapter_and_records_report(tmp_path, make_pdf, monkeypatch):
    class ReviewProvider(FakeProvider):
        def __init__(self, outcomes):
            super().__init__()
            self.outcomes = iter(outcomes)
            self.review_calls = 0

        def review_reflow_page(self, _payload):
            self.review_calls += 1
            status = next(self.outcomes)
            return FormatReviewResult(
                status=status,
                issues=[{"type": "widow_orphan"}] if status == "fail" else [],
            )

        def translate(self, _source, _context, _entities, _glossary):
            return TranslationResult(translation="已翻译的中文段落。")

    monkeypatch.setenv("V2_RENDER_MODE", "reflow")
    source = make_pdf(tmp_path / "reviewed.pdf", paragraphs=["Chapter One", "A paragraph to review."])
    root = tmp_path / "runs"
    db = Database(root / "state.sqlite3")
    local = ReviewProvider(["fail", "fail"])
    remote = ReviewProvider(["fail", "pass"])
    remote.model = "remote-reviewer"
    workflow = Workflow(root, db, None, TranslationCoordinator(local, QualityRouter(), remote))
    run_id = workflow.create(source, "format-review")

    workflow.execute(run_id)

    report = json.loads((root / run_id / "format_review.json").read_text(encoding="utf-8"))
    assert db.run(run_id)["status"] == "completed"
    assert local.review_calls == 2
    assert remote.review_calls == 2
    assert report["status"] == "passed"
    assert report["repair_pass"] == 1
    assert report["repair_history"][0]["chapter_id"] == "chapter-0001"
    assert any(event["stage"] == "remote" for event in report["events"])
    assert any(event["event_type"] == "format_review_remote_completed" for event in db.provider_events(run_id))


def test_provider_authentication_failure_is_sanitized(tmp_path, make_pdf):
    class AuthenticationError(Exception):
        pass

    class AuthenticationFailureProvider(FakeProvider):
        def translate(self, source, context, entities, glossary):
            raise AuthenticationError("invalid key: sk-secret-value")

    source = make_pdf(tmp_path / "book.pdf")
    root = tmp_path / "runs"
    db = Database(root / "state.sqlite3")
    workflow = Workflow(root, db, AuthenticationFailureProvider())
    run_id = workflow.create(source, "request-auth")

    with pytest.raises(WorkflowError) as caught:
        workflow.execute(run_id)

    assert caught.value.error_code == "PROVIDER_AUTHENTICATION_FAILED"
    run = db.run(run_id)
    assert run["error_code"] == "PROVIDER_AUTHENTICATION_FAILED"
    assert "sk-secret-value" not in run["error_message"]
    assert "sk-secret-value" not in (root / run_id / "failure.json").read_text(encoding="utf-8")


def test_corrupt_glossary_artifact_is_recovered_from_database(tmp_path, make_pdf):
    source = make_pdf(tmp_path / "book.pdf")
    root, db, _provider, workflow, run_id = setup_workflow(tmp_path, source)
    (root / run_id / "glossary.json").write_text("{broken", encoding="utf-8")

    workflow.execute(run_id)

    assert db.run(run_id)["status"] == "completed"
    assert json.loads((root / run_id / "glossary.json").read_text(encoding="utf-8")) == [
        {"source": "house", "target": "宅邸"}
    ]


def test_cancel_requested_during_provider_call_wins(tmp_path, make_pdf):
    class CancellingProvider(FakeProvider):
        def __init__(self, db):
            super().__init__()
            self.db = db
            self.run_id = ""

        def translate(self, source, context, entities, glossary):
            self.db.request_cancel(self.run_id)
            return TranslationResult(translation="不会保存")

    source = make_pdf(tmp_path / "book.pdf")
    root = tmp_path / "runs"
    db = Database(root / "state.sqlite3")
    provider = CancellingProvider(db)
    workflow = Workflow(root, db, provider)
    run_id = workflow.create(source, "request-cancel-race")
    provider.run_id = run_id

    workflow.execute(run_id)

    assert db.run(run_id)["status"] == "cancelled"
    assert all(row["translation"] is None for row in db.segments(run_id))


def test_cancel_requested_before_provider_error_wins(tmp_path, make_pdf):
    class AuthenticationError(Exception):
        pass

    class CancellingFailureProvider(FakeProvider):
        def __init__(self, db):
            super().__init__()
            self.db = db
            self.run_id = ""

        def translate(self, source, context, entities, glossary):
            self.db.request_cancel(self.run_id)
            raise AuthenticationError("should not become failed")

    source = make_pdf(tmp_path / "book.pdf")
    root = tmp_path / "runs"
    db = Database(root / "state.sqlite3")
    provider = CancellingFailureProvider(db)
    workflow = Workflow(root, db, provider)
    run_id = workflow.create(source, "request-cancel-error")
    provider.run_id = run_id

    workflow.execute(run_id)

    assert db.run(run_id)["status"] == "cancelled"


def test_entity_name_matching_uses_word_boundaries(tmp_path, make_pdf):
    class WillProvider(FakeProvider):
        def translate(self, source, context, entities, glossary):
            if source == "Will arrived.":
                return TranslationResult(
                    translation="威尔来了。",
                    entity_observations=[
                        EntityObservation(source_name="Will", target_name="威尔")
                    ],
                )
            if source == "She will leave.":
                return TranslationResult(translation="她会离开。")
            if source == "WILL returned.":
                return TranslationResult(
                    translation="威尔回来了。",
                    entity_observations=[
                        EntityObservation(source_name="Will", target_name="威尔")
                    ],
                )
            return TranslationResult(translation="第一章")

    source = make_pdf(
        tmp_path / "book.pdf",
        paragraphs=["Chapter One", "Will arrived.", "She will leave.", "WILL returned."],
    )
    root = tmp_path / "runs"
    db = Database(root / "state.sqlite3")
    workflow = Workflow(root, db, WillProvider())
    run_id = workflow.create(source, "request-will-boundary")

    workflow.execute(run_id)

    assert db.run(run_id)["status"] == "completed"


def test_known_entity_drift_does_not_abort_the_run(tmp_path, make_pdf):
    class DriftingProvider(FakeProvider):
        def translate(self, source, context, entities, glossary):
            if "Elizabeth arrived" in source:
                return TranslationResult(
                    translation="伊丽莎白来了",
                    entity_observations=[
                        EntityObservation(source_name="Elizabeth", target_name="伊丽莎白")
                    ],
                )
            if "Elizabeth left" in source:
                return TranslationResult(translation="艾丽丝走了")
            return TranslationResult(translation="第一章")

    source = make_pdf(
        tmp_path / "book.pdf",
        paragraphs=["Chapter One", "Elizabeth arrived.", "Elizabeth left."],
    )
    root = tmp_path / "runs"
    db = Database(root / "state.sqlite3")
    workflow = Workflow(root, db, DriftingProvider())
    run_id = workflow.create(source, "request-entity-drift")

    workflow.execute(run_id)

    assert db.run(run_id)["status"] == "completed"

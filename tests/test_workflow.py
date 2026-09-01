import json
from pathlib import Path

import pytest

from translator.ast import sha256_file
from translator.db import Database
from translator.models import EntityObservation, TranslationResult
from translator.render import RenderValidationError, render_overlay
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


def test_known_entity_must_reuse_canonical_translation(tmp_path, make_pdf):
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

    with pytest.raises(WorkflowError) as caught:
        workflow.execute(run_id)

    assert caught.value.error_code == "ENTITY_CONSISTENCY_FAILED"
    assert db.run(run_id)["status"] == "failed"

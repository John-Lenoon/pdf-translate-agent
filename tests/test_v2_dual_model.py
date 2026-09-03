import json

import pytest

from translator.db import Database
from translator.models import (
    DocumentAST,
    Page,
    RunModelPlan,
    Segment,
    EntityObservation,
    TranslationCandidate,
    TranslationResult,
)
from translator.provider import LocalModelGpuUnavailableError, OllamaAdapter
from translator.report import write_run_report
from translator.routing import QualityRouter, RiskPolicy, TranslationContext
from translator.coordinator import TranslationCoordinator
from translator.entities import valid_person_observations
from translator.workflow import Workflow


def plan() -> RunModelPlan:
    return RunModelPlan(
        local_endpoint="http://127.0.0.1:11434",
        local_model="qwen3:8b",
        local_context_window=8192,
        local_max_output_tokens=1024,
        prompt_version="v2.1",
        workflow_version="v2.1",
        risk_policy_version="v2.1",
    )


def setup_run(tmp_path):
    root = tmp_path / "runs"
    db = Database(root / "state.sqlite3")
    assert db.create_run("run-1", "book.pdf", "hash", "key-1", "fingerprint-1")
    document_id = db.save_document(
        "run-1", DocumentAST(source_sha256="hash", page_count=1, pages=[Page(number=1, width=100, height=100)])
    )
    db.insert_segments(
        "run-1",
        document_id,
        [
            Segment(
                id="segment-1",
                page_number=1,
                ordinal=1,
                source_text="Elizabeth arrived.",
                bbox_refs=[(1, (10, 10, 90, 40))],
            )
        ],
    )
    return root, db


def test_quality_router_keeps_low_risk_local_candidate():
    decision = QualityRouter().decide(
        TranslationCandidate(
            source="local", text="伊丽莎白到了。", model="qwen3:8b", prompt_version="v2", context_version="v2"
        ),
        TranslationContext(source_text="Elizabeth arrived."),
    )
    assert decision.route == "local_only"
    assert decision.review_status == "not_required"


def test_quality_router_routes_degraded_context_with_calibrated_policy():
    decision = QualityRouter(policy=RiskPolicy()).decide(
        TranslationCandidate(
            source="local", text="伊丽莎白到了。", model="qwen3:8b", prompt_version="v2", context_version="v2"
        ),
        TranslationContext(source_text="Elizabeth arrived.", context_degraded=True),
    )
    assert decision.route == "remote_review"
    assert "context_degraded" in decision.signals


def test_quality_router_keeps_low_risk_local_when_summary_is_disabled():
    decision = QualityRouter(policy=RiskPolicy()).decide(
        TranslationCandidate(
            source="local", text="伊丽莎白到了。", model="qwen3:8b", prompt_version="v2", context_version="v2"
        ),
        TranslationContext(source_text="Elizabeth arrived.", context_degraded=False),
    )
    assert decision.route == "local_only"


def test_risk_policy_rejects_invalid_values():
    with pytest.raises(ValueError):
        RiskPolicy(remote_threshold=1.1)
    with pytest.raises(ValueError):
        RiskPolicy(calibration_interval=0)


def test_quality_router_routes_entity_conflict_to_remote_review():
    decision = QualityRouter().decide(
        TranslationCandidate(
            source="local", text="伊丽莎白到了。", model="qwen3:8b", prompt_version="v2", context_version="v2"
        ),
        TranslationContext(source_text="Elizabeth arrived.", entity_conflict=True),
    )
    assert decision.route == "remote_review"
    assert "entity_conflict" in decision.signals


def test_quality_router_rejects_unchanged_source_as_local_only():
    decision = QualityRouter().decide(
        TranslationCandidate(
            source="local", text="Elizabeth arrived.", model="qwen3:8b", prompt_version="v2", context_version="v2"
        ),
        TranslationContext(source_text="Elizabeth arrived."),
    )
    assert decision.route == "remote_review"
    assert "unchanged_source" in decision.signals


def test_quality_router_calibration_sample_forces_remote_review():
    decision = QualityRouter().decide(
        TranslationCandidate(
            source="local", text="她到了。", model="qwen3:8b", prompt_version="v2", context_version="v2"
        ),
        TranslationContext(source_text="She arrived.", calibration_sample=True),
    )
    assert decision.route == "remote_review"
    assert "calibration_sample" in decision.signals


def test_quality_router_detects_untranslated_and_number_changes():
    decision = QualityRouter().decide(
        TranslationCandidate(
            source="local", text="She has 4 books.", model="qwen3:8b", prompt_version="v2", context_version="v2"
        ),
        TranslationContext(source_text="She has 3 books.", validation_errors=("untranslated_latin", "numbers_changed")),
    )
    assert decision.route == "remote_review"
    assert {"untranslated_latin", "numbers_changed"}.issubset(decision.signals)


def test_entity_filter_rejects_pronouns_and_relationships():
    observations = valid_person_observations([
        EntityObservation(source_name="She", target_name="她"),
        EntityObservation(source_name="her father", target_name="她的父亲"),
        EntityObservation(source_name="Mara", target_name="玛拉"),
    ])
    assert [item.source_name for item in observations] == ["Mara"]


def test_ollama_adapter_probes_and_parses_schema_output():
    calls = []

    def request(method, path, payload):
        calls.append((method, path, payload))
        if path == "/api/tags":
            return {"models": [{"name": "qwen3:8b"}]}
        if path == "/api/ps":
            return {"models": [{"name": "qwen3:8b", "size_vram": 1024}]}
        return {
            "message": {"content": json.dumps({"translation": "译文", "entity_observations": [], "glossary_suggestions": [], "warnings": []})},
            "prompt_eval_count": 12,
            "eval_count": 4,
        }

    adapter = OllamaAdapter("qwen3:8b", request=request)
    adapter.probe()
    result = adapter.translate("Source", {}, [], [])

    assert result.translation == "译文"
    assert adapter.last_metadata["usage"] == {"input_tokens": 12, "output_tokens": 4}
    assert calls[1][2]["format"]["type"] == "object"
    assert calls[1][2]["think"] is False
    assert calls[1][2]["options"]["num_ctx"] == 4096
    assert calls[1][2]["options"]["num_predict"] == 512
    assert "Simplified Chinese" in calls[3][2]["messages"][0]["content"]


def test_ollama_probe_rejects_cpu_only_model():
    def request(method, path, payload):
        if path == "/api/tags":
            return {"models": [{"name": "qwen3:8b"}]}
        if path == "/api/ps":
            return {"models": [{"name": "qwen3:8b", "size_vram": 0}]}
        return {"message": {"content": json.dumps({"translation": "译文"})}}

    with pytest.raises(LocalModelGpuUnavailableError, match="GPU memory"):
        OllamaAdapter("qwen3:8b", request=request).probe()


def test_ollama_adapter_can_cancel_active_response():
    class Response:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    response = Response()
    adapter = OllamaAdapter("qwen3:8b")
    adapter._active_response = response
    adapter.cancel_active_request()
    assert response.closed is True


def test_ollama_format_review_sends_page_as_native_image_input():
    calls = []

    def request(method, path, payload):
        calls.append((method, path, payload))
        return {
            "message": {"content": json.dumps({"status": "pass", "issues": [], "summary": "clean"})},
            "prompt_eval_count": 14,
            "eval_count": 3,
        }

    result = OllamaAdapter("qwen3:8b", request=request).review_reflow_page(
        {"page": 1, "metrics": {"ink_ratio": 0.1}, "screenshot_png_base64": "aGVsbG8="}
    )

    assert result.status == "pass"
    user_message = calls[0][2]["messages"][1]
    assert user_message["images"] == ["aGVsbG8="]
    assert "screenshot_png_base64" not in user_message["content"]


def test_v2_records_are_immutable_and_report_is_regenerated(tmp_path):
    root, db = setup_run(tmp_path)
    plan_hash = db.save_run_model_plan("run-1", plan())
    assert db.save_run_model_plan("run-1", plan()) == plan_hash
    changed = plan().model_copy(update={"local_model": "other"})
    with pytest.raises(ValueError, match="RUN_MODEL_PLAN_MISMATCH"):
        db.save_run_model_plan("run-1", changed)

    candidate = TranslationCandidate(
        source="local", text="伊丽莎白到了。", model="qwen3:8b", prompt_version="v2", context_version="v2"
    )
    db.save_candidate("run-1", "segment-1", candidate, current=True)
    decision = QualityRouter().decide(candidate, TranslationContext(source_text="Elizabeth arrived.", entity_conflict=True))
    db.save_risk_decision("run-1", "segment-1", decision)
    db.provider_event("run-1", "budget_exceeded", {"reserved_tokens": 100})
    db.set_run("run-1", "completed_with_review_debt")

    report_path = write_run_report(root, db, "run-1")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == "v2.1"
    assert report["review_debt"] == ["segment-1"]
    assert report["permitted_next_actions"] == ["continue_remote_review"]
    assert db.queue_run("run-1") == "remote_review_queued"


class HighRiskProvider:
    model = "local-test"
    last_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}

    def __init__(self, text="本地译文"):
        self.text = text
        self.translate_calls = 0

    def summarize_chapter(self, _chapter_text):
        return "章节摘要"

    def translate(self, _source, _context, _entities, _glossary):
        self.translate_calls += 1
        return TranslationResult(translation=self.text, risk_label="high")


def test_workflow_uses_remote_revision_for_high_risk_segment(tmp_path, make_pdf):
    root = tmp_path / "runs"
    db = Database(root / "state.sqlite3")
    local = HighRiskProvider()
    remote = HighRiskProvider("远程修订译文")
    remote.model = "remote-test"
    workflow = Workflow(root, db, None, TranslationCoordinator(local, QualityRouter(), remote))
    run_id = workflow.create(make_pdf(tmp_path / "book.pdf"), "v2-remote")

    workflow.execute(run_id)

    assert db.run(run_id)["status"] == "completed"
    assert remote.translate_calls > 0
    candidates = db.candidates(run_id)
    assert {row["source"] for row in candidates} == {"local", "remote"}
    assert all(row["source"] == "remote" for row in candidates if row["is_current"])
    assert json.loads((root / run_id / "run_report.json").read_text(encoding="utf-8"))["review_debt"] == []


def test_workflow_completes_with_review_debt_without_remote_provider(tmp_path, make_pdf):
    root = tmp_path / "runs"
    db = Database(root / "state.sqlite3")
    local = HighRiskProvider()
    workflow = Workflow(root, db, None, TranslationCoordinator(local, QualityRouter()))
    run_id = workflow.create(make_pdf(tmp_path / "book.pdf"), "v2-debt")

    workflow.execute(run_id)

    assert db.run(run_id)["status"] == "completed_with_review_debt"
    assert (root / run_id / "translated.pdf").is_file()
    report = json.loads((root / run_id / "run_report.json").read_text(encoding="utf-8"))
    assert report["review_debt"]


def test_workflow_rejects_unchanged_model_output(tmp_path, make_pdf):
    root = tmp_path / "runs"
    db = Database(root / "state.sqlite3")
    class EchoProvider(HighRiskProvider):
        def translate(self, source, _context, _entities, _glossary):
            return TranslationResult(translation=source, risk_label="low")

    local = EchoProvider()
    workflow = Workflow(root, db, None, TranslationCoordinator(local, QualityRouter()))
    run_id = workflow.create(make_pdf(tmp_path / "book.pdf"), "unchanged-output")

    with pytest.raises(Exception, match="without translating"):
        workflow.execute(run_id)

    assert db.run(run_id)["status"] == "failed"
    assert db.run(run_id)["error_code"] == "UNCHANGED_TRANSLATION"

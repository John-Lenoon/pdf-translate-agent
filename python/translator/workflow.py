from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path

from .ast import PDFValidationError, parse_pdf, read_ast, sha256_file, write_ast
from .coordinator import TranslationCoordinator
from .db import Database, RunLeaseLostError
from .entities import valid_person_observations
from .models import Segment
from .provider import CONTEXT_VERSION, PROMPT_VERSION, TranslationProvider
from .report import write_run_report
from .render import RenderValidationError, render_overlay
from .reflow import (
    ReflowDocument,
    ReflowRenderError,
    build_reflow_chapters,
    extract_reflow_images,
    inspect_reflow_pdf,
    merge_chapter_pdfs,
    render_html,
    render_reflow_pdf,
)
from .segments import split_segments

WORKFLOW_VERSION = "v1.1"


class WorkflowError(RuntimeError):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


class Workflow:
    def __init__(
        self,
        runs_root: Path,
        db: Database,
        provider: TranslationProvider | None,
        coordinator: TranslationCoordinator | None = None,
    ):
        self.runs_root = runs_root
        self.db = db
        self.coordinator = coordinator
        self.provider = coordinator.local_provider if coordinator else provider
        self.calibration_interval = (
            coordinator.router.policy.calibration_interval if coordinator else 5
        )

    def create(
        self, source_pdf: Path, idempotency_key: str, glossary: list[dict] | None = None
    ) -> str:
        source_hash = sha256_file(source_pdf)
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "source": source_hash,
                    "target_language": "zh-CN",
                    "glossary": glossary or [],
                    "ast_version": "1",
                    "prompt_version": PROMPT_VERSION,
                    "context_version": CONTEXT_VERSION,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode()
        ).hexdigest()
        existing = self.db.run_by_key(idempotency_key)
        if existing:
            if existing["request_fingerprint"] != fingerprint:
                raise ValueError("IDEMPOTENCY_CONFLICT")
            return existing["id"]

        run_id = uuid.uuid4().hex
        created = self.db.create_run(
            run_id,
            str(source_pdf.resolve()),
            source_hash,
            idempotency_key,
            fingerprint,
            glossary,
        )
        if not created:
            existing = self.db.run_by_key(idempotency_key)
            if existing and existing["request_fingerprint"] == fingerprint:
                return existing["id"]
            raise ValueError("IDEMPOTENCY_CONFLICT")
        run_dir = self.runs_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_json(run_dir / "glossary.json", glossary or [])
        return run_id

    def execute(self, run_id: str, worker_id: str = "direct") -> None:
        if self.provider is None:
            raise RuntimeError("Translation provider is required to execute a run")
        run = self.db.run(run_id)
        if not run:
            raise KeyError(run_id)
        source = Path(run["source_path"])
        run_dir = self.runs_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        claimed_worker = worker_id if run["worker_id"] == worker_id else None
        lease_stop = threading.Event()
        lease_thread = None
        if claimed_worker:
            lease_thread = threading.Thread(
                target=self._keep_lease,
                args=(run_id, claimed_worker, lease_stop),
                daemon=True,
            )
            lease_thread.start()
        try:
            if not source.is_file():
                raise WorkflowError("SOURCE_MISSING", "Source PDF no longer exists")
            if sha256_file(source) != run["source_sha256"]:
                raise WorkflowError("SOURCE_CHANGED", "Source PDF changed after run creation")
            self._ensure_v2_model_plan(run_id)
            self._checkpoint(run_id, claimed_worker)

            ast_path = run_dir / "ast.json"
            if ast_path.exists():
                try:
                    ast = read_ast(ast_path)
                except (ValueError, OSError):
                    ast_path.unlink(missing_ok=True)
                    ast = parse_pdf(source)
                    write_ast(ast, ast_path)
                if ast.source_sha256 != run["source_sha256"]:
                    raise WorkflowError("AST_HASH_MISMATCH", "Saved AST does not match source PDF")
            else:
                self.db.set_run(run_id, "parsing", worker_id=claimed_worker)
                ast = parse_pdf(source)
                write_ast(ast, ast_path)

            self._checkpoint(run_id, claimed_worker)
            self.db.set_run(run_id, "segmenting", worker_id=claimed_worker)
            segments = split_segments(ast)
            if not segments:
                raise WorkflowError("NO_SEGMENTS", "PDF contains no translatable segments")
            document_id = self.db.save_document(run_id, ast)
            self.db.insert_segments(run_id, document_id, segments)

            summaries = self._chapter_summaries(
                run_id, run_dir, segments, claimed_worker
            )
            self._checkpoint(run_id, claimed_worker)
            glossary_path = run_dir / "glossary.json"
            try:
                glossary = json.loads(glossary_path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                glossary = json.loads(run["glossary_json"])
                self._atomic_json(glossary_path, glossary)
            self.db.set_run(run_id, "translating", worker_id=claimed_worker)
            for row in self.db.pending_segments(run_id):
                self._checkpoint(run_id, claimed_worker)
                segment = self._segment_from_row(row)
                if self.coordinator:
                    discover = getattr(self.coordinator.local_provider, "discover_entities", None)
                    if discover:
                        try:
                            discovered = discover(segment.source_text, {"chapter_id": segment.chapter_id})
                            for observation in valid_person_observations(discovered.entities):
                                self.db.upsert_entity(run_id, segment.id, observation, claimed_worker)
                        except Exception as exc:
                            self.db.provider_event(run_id, "entity_discovery_failed", {"error_type": type(exc).__name__}, segment.id)
                judgment = self.db.queued_judgment(run_id, segment.id)
                context = {
                    "chapter_summary": summaries.get(segment.chapter_id or "", ""),
                    "context_degraded": (
                        os.getenv("V2_ENABLE_CHAPTER_SUMMARY", "0").strip().lower()
                        in {"1", "true", "yes"}
                        and not summaries.get(segment.chapter_id or "", "")
                    ),
                    "previous_paragraphs": segment.context_before,
                    "next_paragraphs": segment.context_after,
                        "judge_feedback": (
                        {"label": judgment["label"], "notes": judgment["notes"]}
                        if judgment
                        else None
                        ),
                        "calibration_sample": segment.ordinal % self.calibration_interval == 0,
                    }
                entities = [
                    {
                        "source_name": entity["source_name"],
                        "target_name": entity["target_name"],
                        "entity_type": "person",
                    }
                    for entity in self.db.entities(run_id)
                ]
                try:
                    coordination = self._translate_segment(
                        segment, context, entities, glossary, self.db.next_attempt(run_id, segment.id) - 1
                    )
                    result = coordination.result
                    self._checkpoint(run_id, claimed_worker)
                    translation = result.translation.strip()
                    if not translation:
                        raise WorkflowError("EMPTY_TRANSLATION", "Model returned empty translation")
                    if translation.casefold() == segment.source_text.strip().casefold():
                        raise WorkflowError(
                            "UNCHANGED_TRANSLATION",
                            "Model returned the source text without translating it",
                        )
                    entity_issue: str | None = None
                    for observation in valid_person_observations(result.entity_observations):
                        canonical = self.db.upsert_entity(
                            run_id, segment.id, observation, claimed_worker
                        )
                        observed = observation.target_name.strip()
                        if observed != canonical:
                            entity_issue = f"Model did not use canonical person name: {observation.source_name}"
                    for entity in self.db.entities(run_id):
                        mentions = self._person_mentions(
                            segment.source_text, entity["source_name"]
                        )
                        observations = [
                            item
                            for item in result.entity_observations
                            if item.source_name.casefold() == entity["source_name"].casefold()
                        ]
                        if mentions and translation.count(entity["target_name"]) < len(mentions):
                            entity_issue = f"Translation did not reuse canonical person name: {entity['source_name']}"
                        if any(item.target_name.strip() != entity["target_name"] for item in observations):
                            entity_issue = f"Model changed canonical person name: {entity['source_name']}"
                    if entity_issue and self.coordinator:
                        self.db.provider_event(
                            run_id,
                            "entity_consistency_failed",
                            {"message": entity_issue, "action": "kept_candidate_and_continued"},
                            segment.id,
                        )
                        decision = coordination.decision.model_copy(
                            update={
                                "review_status": "review_debt",
                                "signals": sorted(set([*coordination.decision.signals, "entity_consistency_failed"])),
                                "selection_reason": "Entity consistency requires follow-up review",
                            }
                        )
                        coordination = replace(coordination, decision=decision)
                    attempt = self.db.next_attempt(run_id, segment.id)
                    if self.coordinator:
                        for candidate in coordination.candidates:
                            self.db.save_candidate(
                                run_id,
                                segment.id,
                                candidate,
                                current=candidate == coordination.selected,
                            )
                        self.db.save_risk_decision(run_id, segment.id, coordination.decision)
                        for event_type, payload in coordination.provider_events:
                            self.db.provider_event(run_id, event_type, payload, segment.id)
                    self.db.save_translation(
                        run_id,
                        segment.id,
                        translation,
                        coordination.selected.model if self.coordinator else self.provider.model,
                        PROMPT_VERSION,
                        CONTEXT_VERSION,
                        attempt,
                        "remote_review" if self.coordinator and coordination.selected.source == "remote" else ("judge" if judgment else "initial"),
                        {
                            **(coordination.selected.metadata if self.coordinator else self.provider.last_metadata),
                            "workflow_version": WORKFLOW_VERSION,
                            "ast_version": ast.ast_version,
                            "context_source_ordinals": list(
                                range(max(1, segment.ordinal - len(segment.context_before)), segment.ordinal)
                            )
                            + list(
                                range(segment.ordinal + 1, segment.ordinal + 1 + len(segment.context_after))
                            ),
                            "chapter_id": segment.chapter_id,
                            "glossary_suggestions": result.glossary_suggestions,
                            "warnings": result.warnings,
                        },
                        claimed_worker,
                    )
                except RunLeaseLostError:
                    raise
                except WorkflowError:
                    raise
                except Exception as exc:
                    self._check_cancel(run_id)
                    code, message = self._provider_error(exc)
                    self.db.fail_segment(
                        run_id, segment.id, message, claimed_worker
                    )
                    raise WorkflowError(code, message) from exc

            self._materialize_provider_artifacts(run_id, run_dir)
            remaining = [row for row in self.db.segments(run_id) if row["status"] != "translated"]
            if remaining:
                raise WorkflowError("SEGMENTS_INCOMPLETE", "Not all segments are translated")

            self._checkpoint(run_id, claimed_worker)
            self.db.set_run(run_id, "rendering", worker_id=claimed_worker)
            rows = self.db.segments(run_id)
            translations = {row["id"]: row["translation"] for row in rows}
            persisted_segments = [self._segment_from_row(row) for row in rows]
            font_value = os.getenv("TRANSLATION_FONT_PATH", "").strip()
            font_path = Path(font_value) if font_value else None
            if font_path and not font_path.is_file():
                raise WorkflowError("FONT_NOT_FOUND", f"Configured font does not exist: {font_path}")
            format_result = {"status": "not_applicable"}
            if os.getenv("V2_RENDER_MODE", "reflow").strip().lower() == "reflow":
                format_result = self._render_reflow(run_id, source, run_dir, persisted_segments, translations, ast)
            else:
                render_overlay(
                    source,
                    run_dir / "translated.pdf",
                    translations,
                    persisted_segments,
                    ast,
                    font_path=font_path,
                )
            self._checkpoint(run_id, claimed_worker)
            if sha256_file(source) != run["source_sha256"]:
                raise WorkflowError("SOURCE_CHANGED", "Source PDF changed during workflow")
            terminal_status = (
                "completed_with_review_debt"
                if self.db.review_debt_segments(run_id) or format_result.get("status") == "format_review_debt"
                else "completed"
            )
            self.db.set_run(run_id, terminal_status, worker_id=claimed_worker)
            if self.coordinator:
                write_run_report(self.runs_root, self.db, run_id)
        except RunLeaseLostError:
            raise
        except RenderValidationError as exc:
            if self.db.cancel_requested(run_id):
                self.db.set_run(run_id, "cancelled", worker_id=claimed_worker)
                return
            self._atomic_json(run_dir / "render.failure.json", exc.report.model_dump())
            self._write_failure_report(run_dir, exc.issue.error_code, str(exc))
            self.db.set_run(
                run_id, "render_failed", exc.issue.error_code, str(exc), claimed_worker
            )
            raise
        except ReflowRenderError as exc:
            if self.db.cancel_requested(run_id):
                self.db.set_run(run_id, "cancelled", worker_id=claimed_worker)
                return
            self._write_failure_report(run_dir, "REFLOW_RENDER_FAILED", str(exc))
            self.db.set_run(run_id, "render_failed", "REFLOW_RENDER_FAILED", str(exc), claimed_worker)
            raise
        except PDFValidationError as exc:
            if self.db.cancel_requested(run_id):
                self.db.set_run(run_id, "cancelled", worker_id=claimed_worker)
                return
            self._write_failure_report(run_dir, str(exc), str(exc))
            self.db.set_run(run_id, "failed", str(exc), str(exc), claimed_worker)
            raise
        except WorkflowError as exc:
            if exc.error_code == "RUN_LEASE_LOST":
                raise
            if exc.error_code == "CANCELLED" or self.db.cancel_requested(run_id):
                self.db.set_run(run_id, "cancelled", worker_id=claimed_worker)
                return
            self._write_failure_report(run_dir, exc.error_code, str(exc))
            self.db.set_run(run_id, "failed", exc.error_code, str(exc), claimed_worker)
            raise
        except Exception as exc:
            if self.db.cancel_requested(run_id):
                self.db.set_run(run_id, "cancelled", worker_id=claimed_worker)
                return
            self._write_failure_report(run_dir, type(exc).__name__, str(exc))
            self.db.set_run(
                run_id, "failed", "WORKFLOW_FAILED", "Workflow failed. See local runner logs.", claimed_worker
            )
            raise
        finally:
            lease_stop.set()
            if lease_thread:
                lease_thread.join(timeout=2)

    def _chapter_summaries(
        self,
        run_id: str,
        run_dir: Path,
        segments: list[Segment],
        worker_id: str | None,
    ) -> dict[str, str]:
        path = run_dir / "chapter_summaries.json"
        if os.getenv("V2_ENABLE_CHAPTER_SUMMARY", "0").strip().lower() not in {"1", "true", "yes"}:
            self._atomic_json(path, {})
            return {}
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                path.unlink(missing_ok=True)
        chapters: dict[str, list[str]] = {}
        for segment in segments:
            chapters.setdefault(segment.chapter_id or "chapter-0001", []).append(
                segment.source_text
            )
        summaries: dict[str, str] = {}
        for chapter_id, paragraphs in chapters.items():
            self._checkpoint(run_id, worker_id)
            try:
                summaries[chapter_id] = self.provider.summarize_chapter("\n\n".join(paragraphs))
            except Exception as exc:
                summaries[chapter_id] = ""
                _code, message = self._provider_error(exc)
                self.db.mark_context_degraded(
                    run_id, f"{chapter_id}: {message}", worker_id
                )
        self._atomic_json(path, summaries)
        return summaries

    def _translate_segment(
        self, segment: Segment, context: dict, entities: list[dict], glossary: list[dict], retry_count: int
    ):
        if self.coordinator is None:
            result = self.provider.translate(segment.source_text, context, entities, glossary)
            return type("V1Coordination", (), {"result": result, "selected": None})()
        flags = ("cross_page",) if len(segment.bbox_refs) > 1 else ()
        return self.coordinator.translate(
            segment.source_text,
            context,
            entities,
            glossary,
            retry_count=retry_count,
            structural_flags=flags,
        )

    def _render_reflow(
        self,
        run_id: str,
        source: Path,
        run_dir: Path,
        segments: list[Segment],
        translations: dict[str, str],
        ast,
    ) -> dict:
        output = run_dir / "translated.pdf"
        assets = extract_reflow_images(source, ast, run_dir / "reflow-assets")
        reviewer = self.coordinator.local_provider if self.coordinator else None
        document = build_reflow_chapters(
            ast, segments, translations, images=assets, reviewer=reviewer
        )
        self._atomic_json(run_dir / "reflow_document.json", document.artifact())
        first_page = ast.pages[0]
        chapter_dir = run_dir / "reflow-chapters"
        chapter_dir.mkdir(parents=True, exist_ok=True)
        repair_attempts = {chapter.chapter_id: 0 for chapter in document.chapters}
        chapter_paths: dict[str, Path] = {}
        repair_history: list[dict] = []

        def render_chapter(chapter_id: str) -> Path:
            chapter = next(item for item in document.chapters if item.chapter_id == chapter_id)
            chapter_document = ReflowDocument(document.version, document.source_page_count, (chapter,))
            html_text = render_html(
                chapter_document,
                page_width_pt=first_page.width,
                page_height_pt=first_page.height,
                font_family=os.getenv(
                "V2_REFLOW_FONT_FAMILY",
                "Noto Serif CJK SC, Source Han Serif SC, SimSun, serif",
                ),
                font_path=Path(os.getenv("TRANSLATION_FONT_PATH", "")).resolve()
                if os.getenv("TRANSLATION_FONT_PATH", "").strip()
                else None,
                repair_pass=repair_attempts[chapter_id],
            )
            self._atomic_json(chapter_dir / f"{chapter_id}.json", chapter_document.artifact())
            (chapter_dir / f"{chapter_id}.html").write_text(html_text, encoding="utf-8")
            chapter_pdf = chapter_dir / f"{chapter_id}.pdf"
            render_reflow_pdf(html_text, chapter_pdf, page_width_pt=first_page.width, page_height_pt=first_page.height, page_numbers=False)
            return chapter_pdf

        for chapter in document.chapters:
            chapter_paths[chapter.chapter_id] = render_chapter(chapter.chapter_id)

        for pass_number in range(3):
            output.unlink(missing_ok=True)
            merge_chapter_pdfs([chapter_paths[chapter.chapter_id] for chapter in document.chapters], output)
            validation = inspect_reflow_pdf(output, document, run_dir / "reflow-preview")
            review = self._review_reflow_pages(run_id, validation, run_dir)
            review["repair_pass"] = pass_number
            if review["status"] != "format_review_failed":
                result = {
                    **validation,
                    **review,
                    "renderer": "reflow",
                    "source_page_count": ast.page_count,
                    "rendered_segments": len(segments),
                    "structure_decisions": document.artifact(),
                    "repair_history": repair_history,
                }
                self._atomic_json(output.with_suffix(".report.json"), result)
                self._atomic_json(run_dir / "format_review.json", result)
                return result
            failed_pages = {issue.get("page") for issue in review.get("issues", []) if issue.get("page")}
            repair_chapters = {
                chapter.chapter_id
                for chapter in document.chapters
                if any(validation["output_pages"].get(block.segment_id) in failed_pages for block in chapter.blocks if block.segment_id)
            }
            repair_chapters = repair_chapters or {chapter.chapter_id for chapter in document.chapters}
            eligible = {chapter_id for chapter_id in repair_chapters if repair_attempts[chapter_id] < 2}
            if not eligible:
                review["status"] = "format_review_failed"
                self._atomic_json(run_dir / "format_review.json", {**validation, **review})
                raise ReflowRenderError("Format review failed after chapter repair attempts")
            for chapter_id in eligible:
                repair_attempts[chapter_id] += 1
                repair_history.append({
                    "chapter_id": chapter_id,
                    "attempt": repair_attempts[chapter_id],
                    "trigger_pages": sorted(failed_pages),
                    "issues": review.get("issues", []),
                })
                chapter_paths[chapter_id] = render_chapter(chapter_id)
        raise ReflowRenderError("Format review repair loop exhausted")

    def _review_reflow_pages(self, run_id: str, validation: dict, run_dir: Path) -> dict:
        suspicious = [metric for metric in validation["metrics"] if metric["suspicious"]]
        if not self.coordinator:
            return {"status": "not_configured", "issues": [], "reviewed_pages": [], "events": []}
        local = self.coordinator.local_provider
        remote = self.coordinator.remote_provider
        if not callable(getattr(local, "review_reflow_page", None)):
            return {
                "status": "not_configured",
                "issues": [],
                "reviewed_pages": [],
                "debt_pages": [],
                "events": [],
            }
        issues: list[dict] = []
        debt_pages: list[int] = []
        reviewed_pages: list[int] = []
        events: list[dict] = []
        # The local model reviews all pages; remote review is reserved for local failures or metric outliers.
        for metric in validation["metrics"]:
            screenshot = run_dir / "reflow-preview" / metric["screenshot"]
            payload = {"page": metric["page"], "metrics": metric, "screenshot_png_base64": base64.b64encode(screenshot.read_bytes()).decode("ascii")}
            try:
                local_result = local.review_reflow_page(payload)
                reviewed_pages.append(metric["page"])
                event = {"model": getattr(local, "model", "local"), "page": metric["page"], "result": local_result.status, "usage": getattr(local, "last_metadata", {}).get("usage")}
                events.append({"stage": "local", **event})
                self.db.provider_event(run_id, "format_review_local_completed", event)
            except Exception as exc:
                debt_pages.append(metric["page"])
                event = {"model": getattr(local, "model", "local"), "page": metric["page"], "error": str(exc)}
                events.append({"stage": "local", "result": "debt", **event})
                self.db.provider_event(run_id, "format_review_local_failed", event)
                continue
            if local_result.status == "fail" or metric in suspicious:
                if not callable(getattr(remote, "review_reflow_page", None)):
                    debt_pages.append(metric["page"])
                    continue
                try:
                    remote_result = remote.review_reflow_page(payload)
                    event = {"model": getattr(remote, "model", "remote"), "page": metric["page"], "result": remote_result.status, "usage": getattr(remote, "last_metadata", {}).get("usage")}
                    events.append({"stage": "remote", **event})
                    self.db.provider_event(run_id, "format_review_remote_completed", event)
                except Exception as exc:
                    debt_pages.append(metric["page"])
                    event = {"model": getattr(remote, "model", "remote"), "page": metric["page"], "error": str(exc)}
                    events.append({"stage": "remote", "result": "debt", **event})
                    self.db.provider_event(run_id, "format_review_remote_failed", event)
                    continue
                if remote_result.status == "fail":
                    issues.extend([{**issue, "page": issue.get("page", metric["page"])} for issue in remote_result.issues] or [{"page": metric["page"], "type": "model_layout_failure"}])
        if issues:
            return {"status": "format_review_failed", "issues": issues, "reviewed_pages": reviewed_pages, "debt_pages": debt_pages, "events": events}
        if debt_pages:
            return {"status": "format_review_debt", "issues": [], "reviewed_pages": reviewed_pages, "debt_pages": debt_pages, "events": events}
        return {"status": "passed", "issues": [], "reviewed_pages": reviewed_pages, "debt_pages": [], "events": events}

    def _ensure_v2_model_plan(self, run_id: str) -> None:
        if self.coordinator is None or self.db.run_model_plan(run_id):
            return
        local = self.coordinator.local_provider
        endpoint = getattr(local, "endpoint", "")
        from .models import RunModelPlan
        from .routing import RISK_POLICY_VERSION

        plan = RunModelPlan(
            local_endpoint=endpoint,
            local_model=local.model,
            local_context_window=int(getattr(local, "num_ctx", os.getenv("V2_LOCAL_CONTEXT_WINDOW", "4096"))),
            local_max_output_tokens=int(getattr(local, "num_predict", os.getenv("V2_LOCAL_MAX_OUTPUT_TOKENS", "512"))),
            local_batch_concurrency=int(os.getenv("V2_LOCAL_BATCH_CONCURRENCY", "1")),
            remote_adapter="openai_compatible" if self.coordinator.remote_provider else None,
            remote_endpoint=getattr(self.coordinator.remote_provider, "base_url", None),
            remote_model=getattr(self.coordinator.remote_provider, "model", None),
            prompt_version=PROMPT_VERSION,
            workflow_version=WORKFLOW_VERSION,
            risk_policy_version=RISK_POLICY_VERSION,
        )
        self.db.save_run_model_plan(run_id, plan)

    def _keep_lease(self, run_id: str, worker_id: str, stop: threading.Event) -> None:
        last_heartbeat = 0.0
        while not stop.wait(0.25):
            if self.db.cancel_requested(run_id):
                cancel_request = getattr(self.provider, "cancel_active_request", None)
                if cancel_request:
                    cancel_request()
                return
            if time.monotonic() - last_heartbeat >= 5:
                if not self.db.heartbeat(run_id, worker_id):
                    return
                last_heartbeat = time.monotonic()

    def _checkpoint(self, run_id: str, worker_id: str | None) -> None:
        self._check_cancel(run_id)
        if worker_id and not self.db.owns_lease(run_id, worker_id):
            raise WorkflowError("RUN_LEASE_LOST", "Run lease was lost to another worker")

    def _atomic_json(self, path: Path, value) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(path)

    def _materialize_provider_artifacts(self, run_id: str, run_dir: Path) -> None:
        suggestions = []
        warnings = []
        for row in self.db.translation_records(run_id):
            metadata = json.loads(row["metadata_json"])
            suggestions.extend(
                {
                    "segment_id": row["segment_id"],
                    "attempt": row["attempt"],
                    **suggestion,
                }
                for suggestion in metadata.get("glossary_suggestions", [])
            )
            warnings.extend(
                {
                    "segment_id": row["segment_id"],
                    "attempt": row["attempt"],
                    "warning": warning,
                }
                for warning in metadata.get("warnings", [])
            )
        self._atomic_jsonl(run_dir / "glossary_suggestions.jsonl", suggestions)
        self._atomic_jsonl(run_dir / "warnings.jsonl", warnings)

    def _atomic_jsonl(self, path: Path, records: list[dict]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
            encoding="utf-8",
        )
        temporary.replace(path)

    def _check_cancel(self, run_id: str) -> None:
        if self.db.cancel_requested(run_id):
            raise WorkflowError("CANCELLED", "Run was cancelled")

    def _person_mentions(self, source_text: str, source_name: str) -> list[str]:
        matches = re.finditer(
            rf"(?<![A-Za-z]){re.escape(source_name)}(?![A-Za-z])",
            source_text,
            re.IGNORECASE,
        )
        return [
            match.group(0)
            for match in matches
            if match.group(0) == source_name or not match.group(0).islower()
        ]

    def _segment_from_row(self, row) -> Segment:
        return Segment(
            id=row["id"],
            page_number=row["page_number"],
            ordinal=row["ordinal"],
            chapter_id=row["chapter_id"],
            source_text=row["source_text"],
            bbox_refs=json.loads(row["bbox_refs_json"]),
            context_before=json.loads(row["context_before_json"]),
            context_after=json.loads(row["context_after_json"]),
        )

    def _append_jsonl(self, path: Path, records: list[dict]) -> None:
        if not records:
            return
        with path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _write_failure_report(self, run_dir: Path, error_code: str, message: str) -> None:
        (run_dir / "failure.json").write_text(
            json.dumps({"error_code": error_code, "message": message}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _provider_error(self, exc: Exception) -> tuple[str, str]:
        name = type(exc).__name__
        errors = {
            "AuthenticationError": (
                "PROVIDER_AUTHENTICATION_FAILED",
                "OpenAI authentication failed. Check OPENAI_API_KEY and resume the run.",
            ),
            "PermissionDeniedError": (
                "PROVIDER_PERMISSION_DENIED",
                "The configured OpenAI project cannot use this model.",
            ),
            "RateLimitError": (
                "PROVIDER_RATE_LIMITED",
                "OpenAI rate limit persisted after three attempts.",
            ),
            "APIConnectionError": (
                "PROVIDER_CONNECTION_FAILED",
                "OpenAI could not be reached after three attempts.",
            ),
            "APITimeoutError": (
                "PROVIDER_TIMEOUT",
                "OpenAI timed out after three attempts.",
            ),
            "BadRequestError": (
                "PROVIDER_REQUEST_REJECTED",
                "OpenAI rejected the structured translation request.",
            ),
        }
        return errors.get(
            name,
            ("PROVIDER_FAILED", "Translation provider failed. See local runner logs."),
        )

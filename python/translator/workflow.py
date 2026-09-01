from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from pathlib import Path

from .ast import PDFValidationError, parse_pdf, read_ast, sha256_file, write_ast
from .db import Database, RunLeaseLostError
from .models import Segment
from .provider import CONTEXT_VERSION, PROMPT_VERSION, TranslationProvider
from .render import RenderValidationError, render_overlay
from .segments import split_segments

WORKFLOW_VERSION = "v1.1"


class WorkflowError(RuntimeError):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


class Workflow:
    def __init__(self, runs_root: Path, db: Database, provider: TranslationProvider | None):
        self.runs_root = runs_root
        self.db = db
        self.provider = provider

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
                judgment = self.db.queued_judgment(run_id, segment.id)
                context = {
                    "chapter_summary": summaries.get(segment.chapter_id or "", ""),
                    "previous_paragraphs": segment.context_before,
                    "next_paragraphs": segment.context_after,
                    "judge_feedback": (
                        {"label": judgment["label"], "notes": judgment["notes"]}
                        if judgment
                        else None
                    ),
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
                    result = self.provider.translate(
                        segment.source_text, context, entities, glossary
                    )
                    self._checkpoint(run_id, claimed_worker)
                    translation = result.translation.strip()
                    if not translation:
                        raise WorkflowError("EMPTY_TRANSLATION", "Model returned empty translation")
                    for observation in result.entity_observations:
                        canonical = self.db.upsert_entity(
                            run_id, segment.id, observation, claimed_worker
                        )
                        observed = observation.target_name.strip()
                        if observed != canonical:
                            raise WorkflowError(
                                "ENTITY_CONSISTENCY_FAILED",
                                f"Model did not use canonical person name: {observation.source_name}",
                            )
                    for entity in self.db.entities(run_id):
                        mentions = self._person_mentions(
                            segment.source_text, entity["source_name"]
                        )
                        observations = [
                            item
                            for item in result.entity_observations
                            if item.source_name.casefold() == entity["source_name"].casefold()
                        ]
                        if mentions and (
                            translation.count(entity["target_name"]) < len(mentions)
                            or len(observations) < len(mentions)
                            or any(
                                item.target_name.strip() != entity["target_name"]
                                for item in observations
                            )
                        ):
                            raise WorkflowError(
                                "ENTITY_CONSISTENCY_FAILED",
                                f"Translation did not reuse canonical person name: {entity['source_name']}",
                            )
                    attempt = self.db.next_attempt(run_id, segment.id)
                    self.db.save_translation(
                        run_id,
                        segment.id,
                        translation,
                        self.provider.model,
                        PROMPT_VERSION,
                        CONTEXT_VERSION,
                        attempt,
                        "judge" if judgment else "initial",
                        {
                            **self.provider.last_metadata,
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
            self.db.set_run(run_id, "completed", worker_id=claimed_worker)
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

    def _keep_lease(self, run_id: str, worker_id: str, stop: threading.Event) -> None:
        while not stop.wait(5):
            if not self.db.heartbeat(run_id, worker_id):
                return

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

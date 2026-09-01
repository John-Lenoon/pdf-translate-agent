from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .db import ACTIVE_STATUSES, Database
from .workflow import Workflow

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class APIError(Exception):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        *,
        run_id: str | None = None,
        segment_id: str | None = None,
    ):
        self.status_code = status_code
        self.payload = {
            "error_code": error_code,
            "message": message,
            "run_id": run_id,
            "segment_id": segment_id,
        }


class CreateRunRequest(BaseModel):
    source_pdf: str
    idempotency_key: str = Field(min_length=1, max_length=200)
    glossary: list[dict[str, str]] = Field(default_factory=list)


class JudgmentRequest(BaseModel):
    label: Literal["ok", "fidelity", "coherence", "entity", "formatting", "other"]
    notes: str = Field(default="", max_length=4000)


def create_app(runs_root: Path | None = None) -> FastAPI:
    root = runs_root or Path(os.getenv("TRANSLATOR_RUNS_ROOT", "runs"))
    db = Database(root / "state.sqlite3")
    app = FastAPI(title="PDF Translate Agent", version="0.1.0")
    app.state.root = root
    app.state.db = db
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(APIError)
    async def api_error_handler(_request: Request, exc: APIError):
        return JSONResponse(status_code=exc.status_code, content=exc.payload)

    def require_run(run_id: str):
        row = db.run(run_id)
        if not row:
            raise APIError(404, "RUN_NOT_FOUND", "Run not found", run_id=run_id)
        return row

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "model_configured": bool(os.getenv("TRANSLATION_MODEL")),
        }

    @app.post("/runs", status_code=201)
    def create_run(request: CreateRunRequest):
        path = Path(request.source_pdf).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() != ".pdf":
            raise APIError(400, "INVALID_SOURCE_PDF", "source_pdf must be an existing PDF")
        try:
            run_id = Workflow(root, db, None).create(
                path, request.idempotency_key, request.glossary
            )
            return {"run_id": run_id}
        except ValueError as exc:
            raise APIError(409, str(exc), "Idempotency key conflicts with another request") from exc

    @app.post("/runs/upload", status_code=201)
    async def upload_run(
        file: UploadFile = File(...),
        idempotency_key: str = Form(..., min_length=1, max_length=200),
        glossary: str = Form("[]"),
    ):
        filename = file.filename or ""
        if Path(filename).suffix.lower() != ".pdf":
            raise APIError(400, "INVALID_SOURCE_PDF", "Upload must be a PDF file")
        try:
            glossary_value = json.loads(glossary)
        except json.JSONDecodeError as exc:
            raise APIError(400, "INVALID_GLOSSARY", "Glossary must be valid JSON") from exc
        if not isinstance(glossary_value, list):
            raise APIError(400, "INVALID_GLOSSARY", "Glossary must be a JSON array")

        upload_dir = root / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        path = upload_dir / f"{uuid.uuid4().hex}.pdf"
        try:
            with path.open("wb") as destination:
                shutil.copyfileobj(file.file, destination)
            with path.open("rb") as source_file:
                if source_file.read(5) != b"%PDF-":
                    raise APIError(400, "INVALID_SOURCE_PDF", "Uploaded file is not a valid PDF")
            run_id = Workflow(root, db, None).create(path, idempotency_key, glossary_value)
            return {"run_id": run_id}
        except ValueError as exc:
            path.unlink(missing_ok=True)
            raise APIError(409, str(exc), "Idempotency key conflicts with another request") from exc
        except APIError:
            path.unlink(missing_ok=True)
            raise
        except Exception as exc:
            path.unlink(missing_ok=True)
            raise APIError(400, "INVALID_SOURCE_PDF", "Uploaded PDF could not be read") from exc
        finally:
            await file.close()

    @app.get("/runs/{run_id}")
    def get_run(run_id: str):
        row = require_run(run_id)
        segments = db.segments(run_id)
        return {
            "id": row["id"],
            "status": row["status"],
            "error_code": row["error_code"],
            "error_message": row["error_message"],
            "context_degraded": bool(row["context_degraded"]),
            "progress": {
                "done": sum(segment["status"] == "translated" for segment in segments),
                "total": len(segments),
            },
        }

    @app.post("/runs/{run_id}/start")
    def start_run(run_id: str):
        require_run(run_id)
        status = db.queue_run(run_id)
        return {
            "run_id": run_id,
            "accepted": status in {"created", "retranslate_queued", *ACTIVE_STATUSES},
            "status": status,
        }

    @app.post("/runs/{run_id}/cancel")
    def cancel_run(run_id: str):
        require_run(run_id)
        accepted = db.request_cancel(run_id)
        return {"run_id": run_id, "accepted": accepted}

    @app.get("/runs/{run_id}/segments")
    def get_segments(run_id: str):
        require_run(run_id)
        result = []
        for row in db.segments(run_id):
            item = dict(row)
            item["bbox_refs"] = json.loads(item.pop("bbox_refs_json"))
            item["context_before"] = json.loads(item.pop("context_before_json"))
            item["context_after"] = json.loads(item.pop("context_after_json"))
            result.append(item)
        return result

    @app.get("/runs/{run_id}/entities")
    def get_entities(run_id: str):
        require_run(run_id)
        return [dict(row) for row in db.entities(run_id)]

    @app.post("/runs/{run_id}/segments/{segment_id}/retranslate")
    def retranslate(run_id: str, segment_id: str, request: JudgmentRequest):
        run = require_run(run_id)
        if run["status"] not in {"completed", "retranslate_queued"}:
            raise APIError(
                409,
                "REVIEW_NOT_AVAILABLE",
                "Judge review is available after translation completes",
                run_id=run_id,
                segment_id=segment_id,
            )
        try:
            status = db.record_judgment(
                run_id, segment_id, request.label, request.notes.strip()
            )
        except KeyError as exc:
            raise APIError(
                404,
                "SEGMENT_NOT_FOUND",
                "Segment not found",
                run_id=run_id,
                segment_id=segment_id,
            ) from exc
        return {"segment_id": segment_id, "status": status}

    @app.get("/runs/{run_id}/events")
    def get_events(run_id: str, after: int = 0):
        require_run(run_id)
        return [
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in db.events(run_id, after)
        ]

    @app.get("/runs/{run_id}/artifacts")
    def artifacts(run_id: str):
        run = require_run(run_id)
        directory = root / run_id
        files = []
        if directory.exists():
            for path in sorted(directory.iterdir()):
                if run["status"] != "completed" and path.name in {
                    "translated.pdf",
                    "translated.report.json",
                }:
                    continue
                if path.is_file():
                    files.append(
                        {
                            "name": path.name,
                            "size": path.stat().st_size,
                            "download_url": f"/runs/{run_id}/artifacts/{path.name}",
                        }
                    )
        return {"files": files}

    @app.get("/runs/{run_id}/artifacts/{name}")
    def download_artifact(run_id: str, name: str):
        run = require_run(run_id)
        if run["status"] != "completed" and name in {
            "translated.pdf",
            "translated.report.json",
        }:
            raise APIError(409, "ARTIFACT_STALE", "Translated PDF is not current", run_id=run_id)
        directory = (root / run_id).resolve()
        path = (directory / name).resolve()
        if path.parent != directory or not path.is_file():
            raise APIError(404, "ARTIFACT_NOT_FOUND", "Artifact not found", run_id=run_id)
        return FileResponse(path, filename=path.name)

    return app


app = create_app()

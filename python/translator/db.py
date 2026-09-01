from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .models import DocumentAST, EntityObservation, Segment

ACTIVE_STATUSES = {"parsing", "segmenting", "translating", "rendering"}
CLAIMABLE_STATUSES = {"created", "retranslate_queued"}


class RunLeaseLostError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self) -> None:
        migration_dir = Path(__file__).with_name("migrations")
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            for migration in sorted(migration_dir.glob("*.sql")):
                version = migration.stem.split("_", 1)[0]
                applied = connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=?", (version,)
                ).fetchone()
                if applied:
                    continue
                connection.executescript(migration.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?)", (version, now())
                )

    def fetchone(self, query: str, parameters: tuple = ()):
        with self.connect() as connection:
            return connection.execute(query, parameters).fetchone()

    def fetchall(self, query: str, parameters: tuple = ()):
        with self.connect() as connection:
            return connection.execute(query, parameters).fetchall()

    def create_run(
        self,
        run_id: str,
        source_path: str,
        source_sha256: str,
        idempotency_key: str,
        request_fingerprint: str,
        glossary: list[dict] | None = None,
    ) -> bool:
        stamp = now()
        try:
            with self.transaction(immediate=True) as connection:
                connection.execute(
                    "INSERT INTO runs(id,source_path,source_sha256,status,idempotency_key,"
                    "request_fingerprint,glossary_json,created_at,updated_at) "
                    "VALUES(?,?,?,'created',?,?,?,?,?)",
                    (
                        run_id,
                        source_path,
                        source_sha256,
                        idempotency_key,
                        request_fingerprint,
                        json.dumps(glossary or [], ensure_ascii=False),
                        stamp,
                        stamp,
                    ),
                )
                self._event(connection, run_id, "run_created", {"status": "created"})
            return True
        except sqlite3.IntegrityError:
            return False

    def run_by_key(self, key: str):
        return self.fetchone("SELECT * FROM runs WHERE idempotency_key=?", (key,))

    def run(self, run_id: str):
        return self.fetchone("SELECT * FROM runs WHERE id=?", (run_id,))

    def set_run(
        self,
        run_id: str,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
        worker_id: str | None = None,
    ) -> None:
        with self.transaction(immediate=True) as connection:
            self._assert_owner(connection, run_id, worker_id)
            connection.execute(
                "UPDATE runs SET status=?,error_code=?,error_message=?,updated_at=? WHERE id=?",
                (status, error_code, error_message, now(), run_id),
            )
            self._event(
                connection,
                run_id,
                "run_status",
                {"status": status, "error_code": error_code, "message": error_message},
            )

    def mark_context_degraded(
        self, run_id: str, message: str, worker_id: str | None = None
    ) -> None:
        with self.transaction(immediate=True) as connection:
            self._assert_owner(connection, run_id, worker_id)
            connection.execute(
                "UPDATE runs SET context_degraded=1,updated_at=? WHERE id=?", (now(), run_id)
            )
            self._event(connection, run_id, "context_degraded", {"message": message})

    def save_document(self, run_id: str, ast: DocumentAST) -> str:
        document_id = hashlib.sha256(f"{run_id}:{ast.source_sha256}".encode()).hexdigest()[:24]
        with self.transaction(immediate=True) as connection:
            connection.execute(
                "INSERT INTO documents(id,run_id,page_count,ast_version,source_metadata_json) "
                "VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "page_count=excluded.page_count,ast_version=excluded.ast_version,"
                "source_metadata_json=excluded.source_metadata_json",
                (
                    document_id,
                    run_id,
                    ast.page_count,
                    ast.ast_version,
                    json.dumps(ast.source_metadata, ensure_ascii=False),
                ),
            )
        return document_id

    def insert_segments(self, run_id: str, document_id: str, segments: list[Segment]) -> None:
        with self.transaction(immediate=True) as connection:
            connection.executemany(
                "INSERT INTO segments(run_id,id,document_id,chapter_id,page_number,ordinal,"
                "source_text,source_hash,bbox_refs_json,context_before_json,context_after_json,status) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,'pending') "
                "ON CONFLICT(run_id,id) DO NOTHING",
                [
                    (
                        run_id,
                        segment.id,
                        document_id,
                        segment.chapter_id,
                        segment.page_number,
                        segment.ordinal,
                        segment.source_text,
                        hashlib.sha256(segment.source_text.encode()).hexdigest(),
                        json.dumps(segment.bbox_refs),
                        json.dumps(segment.context_before, ensure_ascii=False),
                        json.dumps(segment.context_after, ensure_ascii=False),
                    )
                    for segment in segments
                ],
            )

    def segments(self, run_id: str):
        return self.fetchall(
            "SELECT s.*,t.text AS translation,t.attempt,t.model,t.prompt_version,t.context_version "
            "FROM segments s LEFT JOIN translations t ON t.run_id=s.run_id "
            "AND t.segment_id=s.id AND t.is_current=1 WHERE s.run_id=? ORDER BY s.ordinal",
            (run_id,),
        )

    def pending_segments(self, run_id: str):
        return self.fetchall(
            "SELECT * FROM segments WHERE run_id=? AND status IN ('pending','failed','retranslate_queued') "
            "ORDER BY ordinal",
            (run_id,),
        )

    def save_translation(
        self,
        run_id: str,
        segment_id: str,
        text: str,
        model: str,
        prompt_version: str,
        context_version: str,
        attempt: int,
        reason: str,
        metadata: dict,
        worker_id: str | None = None,
    ) -> None:
        with self.transaction(immediate=True) as connection:
            if worker_id:
                owner = connection.execute(
                    "SELECT 1 FROM runs WHERE id=? AND worker_id=? AND lease_until>?",
                    (run_id, worker_id, time.time()),
                ).fetchone()
                if not owner:
                    raise RunLeaseLostError("RUN_LEASE_LOST")
            connection.execute(
                "UPDATE translations SET is_current=0 WHERE run_id=? AND segment_id=?",
                (run_id, segment_id),
            )
            connection.execute(
                "INSERT INTO translations(run_id,segment_id,text,model,prompt_version,context_version,"
                "attempt,reason,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    segment_id,
                    text,
                    model,
                    prompt_version,
                    context_version,
                    attempt,
                    reason,
                    json.dumps(metadata, ensure_ascii=False),
                    now(),
                ),
            )
            connection.execute(
                "UPDATE segments SET status='translated',last_error=NULL WHERE run_id=? AND id=?",
                (run_id, segment_id),
            )
            connection.execute(
                "UPDATE judgments SET status='processed',processed_at=? "
                "WHERE run_id=? AND segment_id=? AND status='queued'",
                (now(), run_id, segment_id),
            )
            self._event(connection, run_id, "segment_translated", {"segment_id": segment_id})

    def next_attempt(self, run_id: str, segment_id: str) -> int:
        row = self.fetchone(
            "SELECT COALESCE(MAX(attempt),0)+1 AS attempt FROM translations "
            "WHERE run_id=? AND segment_id=?",
            (run_id, segment_id),
        )
        return int(row["attempt"])

    def fail_segment(
        self, run_id: str, segment_id: str, message: str, worker_id: str | None = None
    ) -> None:
        with self.transaction(immediate=True) as connection:
            self._assert_owner(connection, run_id, worker_id)
            connection.execute(
                "UPDATE segments SET status='failed',last_error=? WHERE run_id=? AND id=?",
                (message, run_id, segment_id),
            )

    def upsert_entity(
        self,
        run_id: str,
        segment_id: str,
        observation: EntityObservation,
        worker_id: str | None = None,
    ) -> str:
        normalized = " ".join(
            unicodedata.normalize("NFKC", observation.source_name).casefold().split()
        )
        stamp = now()
        with self.transaction(immediate=True) as connection:
            self._assert_owner(connection, run_id, worker_id)
            row = connection.execute(
                "SELECT target_name FROM entities WHERE run_id=? AND entity_type='person' "
                "AND normalized_source_name=?",
                (run_id, normalized),
            ).fetchone()
            if row:
                canonical = row["target_name"]
            else:
                canonical = observation.target_name.strip()
                connection.execute(
                    "INSERT INTO entities(run_id,entity_type,source_name,normalized_source_name,target_name,"
                    "first_segment_id,created_at,updated_at) VALUES(?,'person',?,?,?,?,?,?)",
                    (
                        run_id,
                        observation.source_name.strip(),
                        normalized,
                        canonical,
                        segment_id,
                        stamp,
                        stamp,
                    ),
                )
            connection.execute(
                "INSERT INTO entity_observations(run_id,segment_id,source_name,observed_target_name,"
                "canonical_target_name,evidence_text,created_at) VALUES(?,?,?,?,?,?,?)",
                (
                    run_id,
                    segment_id,
                    observation.source_name,
                    observation.target_name,
                    canonical,
                    observation.evidence_text,
                    stamp,
                ),
            )
            return canonical

    def entities(self, run_id: str):
        return self.fetchall("SELECT * FROM entities WHERE run_id=? ORDER BY id", (run_id,))

    def record_judgment(
        self, run_id: str, segment_id: str, label: str, notes: str
    ) -> str:
        with self.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT status FROM segments WHERE run_id=? AND id=?", (run_id, segment_id)
            ).fetchone()
            if not row:
                raise KeyError(segment_id)
            connection.execute(
                "INSERT INTO judgments(run_id,segment_id,label,notes,status,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (
                    run_id,
                    segment_id,
                    label,
                    notes,
                    "processed" if label == "ok" else "queued",
                    now(),
                ),
            )
            if label == "ok":
                return row["status"]
            connection.execute(
                "UPDATE segments SET status='retranslate_queued' WHERE run_id=? AND id=?",
                (run_id, segment_id),
            )
            connection.execute(
                "UPDATE runs SET status='retranslate_queued',updated_at=? WHERE id=?",
                (now(), run_id),
            )
            self._event(
                connection,
                run_id,
                "retranslation_queued",
                {"segment_id": segment_id, "label": label, "notes": notes},
            )
        return "retranslate_queued"

    def queued_judgment(self, run_id: str, segment_id: str):
        return self.fetchone(
            "SELECT * FROM judgments WHERE run_id=? AND segment_id=? AND status='queued' "
            "ORDER BY id DESC LIMIT 1",
            (run_id, segment_id),
        )

    def request_cancel(self, run_id: str) -> bool:
        with self.transaction(immediate=True) as connection:
            row = connection.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            if row["status"] in {"completed", "cancelled"}:
                return False
            connection.execute(
                "UPDATE runs SET status='cancel_requested',updated_at=? WHERE id=?", (now(), run_id)
            )
            self._event(connection, run_id, "cancel_requested", {})
            return True

    def queue_run(self, run_id: str) -> str:
        with self.transaction(immediate=True) as connection:
            row = connection.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            status = row["status"]
            if status in ACTIVE_STATUSES or status in {"created", "retranslate_queued"}:
                return status
            if status == "completed":
                return status
            connection.execute(
                "UPDATE runs SET status='created',error_code=NULL,error_message=NULL,updated_at=? "
                "WHERE id=?",
                (now(), run_id),
            )
            self._event(connection, run_id, "run_queued", {"previous_status": status})
            return "created"

    def cancel_requested(self, run_id: str) -> bool:
        row = self.run(run_id)
        return bool(row and row["status"] == "cancel_requested")

    def claim_run(self, worker_id: str, lease_seconds: float = 30) -> str | None:
        current = time.time()
        with self.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT id,status FROM runs WHERE "
                "status IN ('created','retranslate_queued') OR "
                "(status IN ('parsing','segmenting','translating','rendering') AND "
                "(lease_until IS NULL OR lease_until<?)) ORDER BY created_at LIMIT 1",
                (current,),
            ).fetchone()
            if not row:
                return None
            connection.execute(
                "UPDATE runs SET worker_id=?,lease_until=?,heartbeat_at=?,updated_at=? WHERE id=?",
                (worker_id, current + lease_seconds, now(), now(), row["id"]),
            )
            self._event(connection, row["id"], "run_claimed", {"worker_id": worker_id})
            return row["id"]

    def heartbeat(self, run_id: str, worker_id: str, lease_seconds: float = 30) -> bool:
        with self.transaction(immediate=True) as connection:
            cursor = connection.execute(
                "UPDATE runs SET lease_until=?,heartbeat_at=?,updated_at=? "
                "WHERE id=? AND worker_id=?",
                (time.time() + lease_seconds, now(), now(), run_id, worker_id),
            )
            return cursor.rowcount == 1

    def owns_lease(self, run_id: str, worker_id: str) -> bool:
        row = self.fetchone(
            "SELECT 1 FROM runs WHERE id=? AND worker_id=? AND lease_until>?",
            (run_id, worker_id, time.time()),
        )
        return row is not None

    def release(self, run_id: str, worker_id: str) -> None:
        with self.transaction(immediate=True) as connection:
            connection.execute(
                "UPDATE runs SET worker_id=NULL,lease_until=NULL,updated_at=? "
                "WHERE id=? AND worker_id=?",
                (now(), run_id, worker_id),
            )

    def events(self, run_id: str, after: int = 0):
        return self.fetchall(
            "SELECT * FROM events WHERE run_id=? AND id>? ORDER BY id", (run_id, after)
        )

    def translation_records(self, run_id: str):
        return self.fetchall(
            "SELECT segment_id,attempt,metadata_json FROM translations "
            "WHERE run_id=? AND is_current=1 ORDER BY segment_id",
            (run_id,),
        )

    def _assert_owner(
        self, connection: sqlite3.Connection, run_id: str, worker_id: str | None
    ) -> None:
        if not worker_id:
            return
        owner = connection.execute(
            "SELECT 1 FROM runs WHERE id=? AND worker_id=? AND lease_until>?",
            (run_id, worker_id, time.time()),
        ).fetchone()
        if not owner:
            raise RunLeaseLostError("RUN_LEASE_LOST")

    def _event(
        self, connection: sqlite3.Connection, run_id: str, event_type: str, payload: dict
    ) -> None:
        connection.execute(
            "INSERT INTO events(run_id,event_type,payload_json,created_at) VALUES(?,?,?,?)",
            (run_id, event_type, json.dumps(payload, ensure_ascii=False), now()),
        )

from pathlib import Path

import pytest

from translator.db import Database
from translator.models import DocumentAST, EntityObservation, Page, Segment


def segment(identifier: str = "same", ordinal: int = 1) -> Segment:
    return Segment(
        id=identifier,
        page_number=1,
        ordinal=ordinal,
        chapter_id="chapter-0001",
        source_text=f"Paragraph {ordinal}",
        bbox_refs=[(1, (10, 10, 100, 50))],
    )


def add_run(db: Database, run_id: str, key: str) -> None:
    assert db.create_run(run_id, "book.pdf", "hash", key, f"fingerprint-{key}")
    ast = DocumentAST(source_sha256="hash", page_count=1, pages=[Page(number=1, width=100, height=100)])
    document_id = db.save_document(run_id, ast)
    db.insert_segments(run_id, document_id, [segment()])


def test_segment_identity_is_scoped_to_run(tmp_path: Path):
    db = Database(tmp_path / "state.sqlite3")
    add_run(db, "r1", "k1")
    add_run(db, "r2", "k2")

    assert len(db.segments("r1")) == 1
    assert len(db.segments("r2")) == 1


def test_expired_lease_is_reclaimed(tmp_path: Path):
    db = Database(tmp_path / "state.sqlite3")
    assert db.create_run("r1", "book.pdf", "hash", "k1", "fingerprint")

    assert db.claim_run("worker-1", lease_seconds=-1) == "r1"
    assert db.claim_run("worker-2") == "r1"
    assert db.run("r1")["worker_id"] == "worker-2"


def test_judgment_queues_only_selected_segment(tmp_path: Path):
    db = Database(tmp_path / "state.sqlite3")
    assert db.create_run("r1", "book.pdf", "hash", "k1", "fingerprint")
    ast = DocumentAST(source_sha256="hash", page_count=1, pages=[Page(number=1, width=100, height=100)])
    document_id = db.save_document("r1", ast)
    db.insert_segments("r1", document_id, [segment("s1", 1), segment("s2", 2)])
    db.set_run("r1", "completed")

    assert db.record_judgment("r1", "s2", "fidelity", "Meaning drifted") == "retranslate_queued"
    statuses = {row["id"]: row["status"] for row in db.segments("r1")}
    assert statuses == {"s1": "pending", "s2": "retranslate_queued"}
    assert db.run("r1")["status"] == "retranslate_queued"


def test_entity_upsert_keeps_first_canonical(tmp_path: Path):
    db = Database(tmp_path / "state.sqlite3")
    add_run(db, "r1", "k1")
    first = EntityObservation(source_name=" Elizabeth ", target_name="伊丽莎白")
    later = EntityObservation(source_name="Elizabeth", target_name="伊丽莎白·班纳特")

    assert db.upsert_entity("r1", "same", first) == "伊丽莎白"
    assert db.upsert_entity("r1", "same", later) == "伊丽莎白"
    assert len(db.entities("r1")) == 1


def test_stale_worker_cannot_save_translation(tmp_path: Path):
    db = Database(tmp_path / "state.sqlite3")
    add_run(db, "r1", "k1")
    assert db.claim_run("old-worker", lease_seconds=-1) == "r1"
    assert db.claim_run("new-worker") == "r1"

    with pytest.raises(RuntimeError, match="RUN_LEASE_LOST"):
        db.save_translation(
            "r1",
            "same",
            "译文",
            "test-model",
            "prompt-v1",
            "context-v1",
            1,
            "initial",
            {},
            "old-worker",
        )

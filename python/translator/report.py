from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .db import Database


REPORT_SCHEMA_VERSION = "v2.1"


def write_run_report(runs_root: Path, db: Database, run_id: str) -> Path:
    run = db.run(run_id)
    if not run:
        raise KeyError(run_id)
    plan = db.run_model_plan(run_id)
    segments = []
    for row in db.segments(run_id):
        decision = db.risk_decision(run_id, row["id"])
        segments.append(
            {
                "id": row["id"],
                "ordinal": row["ordinal"],
                "status": row["status"],
                "candidate_ids": [candidate["id"] for candidate in db.candidates(run_id, row["id"])],
                "risk_decision": json.loads(decision["decision_json"]) if decision else None,
            }
        )
    debt = [segment["id"] for segment in segments if segment["risk_decision"] and segment["risk_decision"]["review_status"] == "review_debt"]
    payload = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "status": run["status"],
        "error_code": run["error_code"],
        "model_plan": {"hash": plan["plan_hash"]} if plan else None,
        "permitted_next_actions": ["continue_remote_review"] if run["status"] == "completed_with_review_debt" else [],
        "review_debt": debt,
        "segments": segments,
        "provider_events": [
            {"type": event["event_type"], "segment_id": event["segment_id"], "payload": json.loads(event["payload_json"])}
            for event in db.provider_events(run_id)
        ],
        "remote_review_summary": {
            "requested": sum(1 for event in db.provider_events(run_id) if event["event_type"] == "remote_review_started"),
            "completed": sum(1 for event in db.provider_events(run_id) if event["event_type"] == "remote_review_completed"),
            "failed": sum(1 for event in db.provider_events(run_id) if event["event_type"] == "remote_review_failed"),
        },
    }
    directory = runs_root / run_id
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "run_report.json"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        temp_path = Path(handle.name)
    os.replace(temp_path, target)
    return target

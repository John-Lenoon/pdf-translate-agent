import argparse
import os
import socket
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

from .db import Database
from .provider import OpenAIProvider
from .workflow import Workflow


def run_once(db: Database, workflow: Workflow, worker_id: str) -> bool:
    run_id = db.claim_run(worker_id)
    if not run_id:
        return False
    try:
        workflow.execute(run_id, worker_id)
    except Exception as exc:
        print(f"run {run_id} failed: {exc}")
    finally:
        db.release(run_id, worker_id)
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process current work then exit")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    root = Path(os.getenv("TRANSLATOR_RUNS_ROOT", "runs"))
    db = Database(root / "state.sqlite3")
    workflow = Workflow(root, db, OpenAIProvider())
    worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    while True:
        processed = run_once(db, workflow, worker_id)
        if args.once and not processed:
            return
        if not processed:
            time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()

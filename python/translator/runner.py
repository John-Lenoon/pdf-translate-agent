import argparse
import os
import socket
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

from .db import Database
from .coordinator import TranslationCoordinator
from .provider import OllamaAdapter, OpenAIProvider
from .routing import QualityRouter, RiskPolicy
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
    local_model = os.getenv("V2_LOCAL_MODEL", "").strip()
    if not local_model:
        workflow = Workflow(root, db, OpenAIProvider())
        worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        while True:
            processed = run_once(db, workflow, worker_id)
            if args.once and not processed:
                return
            if not processed:
                time.sleep(args.poll_interval)
        return
    local = OllamaAdapter(
        local_model,
        os.getenv("V2_OLLAMA_ENDPOINT", "http://127.0.0.1:11434"),
        num_ctx=int(os.getenv("V2_LOCAL_CONTEXT_WINDOW", "4096")),
        num_predict=int(os.getenv("V2_LOCAL_MAX_OUTPUT_TOKENS", "512")),
    )
    try:
        local.probe()
    except Exception as exc:
        code = getattr(exc, "error_code", "local_model_probe_failed")
        raise SystemExit(f"Runner readiness failed [{code}]: {exc}") from exc
    # Keep the V2 name explicit, but honor the existing provider setting so a
    # configured remote model cannot be silently disabled by the runner.
    remote_model = (
        os.getenv("V2_REMOTE_MODEL", "").strip()
        or os.getenv("TRANSLATION_MODEL", "").strip()
    )
    remote = OpenAIProvider(remote_model) if remote_model else None
    workflow = Workflow(
        root, db, None,
        TranslationCoordinator(local, QualityRouter(policy=RiskPolicy.from_environment()), remote),
    )
    worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    while True:
        processed = run_once(db, workflow, worker_id)
        if args.once and not processed:
            return
        if not processed:
            time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()

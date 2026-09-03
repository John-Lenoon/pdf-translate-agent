CREATE TABLE run_model_plans (
  run_id TEXT PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
  plan_hash TEXT NOT NULL,
  plan_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE translation_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  segment_id TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('local','remote')),
  text TEXT NOT NULL,
  model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  context_version TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  is_current INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  FOREIGN KEY (run_id, segment_id) REFERENCES segments(run_id, id) ON DELETE CASCADE
);

CREATE TABLE risk_decisions (
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  segment_id TEXT NOT NULL,
  decision_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (run_id, segment_id),
  FOREIGN KEY (run_id, segment_id) REFERENCES segments(run_id, id) ON DELETE CASCADE
);

CREATE TABLE provider_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  segment_id TEXT,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_candidates_current ON translation_candidates(run_id, segment_id) WHERE is_current = 1;
CREATE INDEX idx_provider_events_run ON provider_events(run_id, id);

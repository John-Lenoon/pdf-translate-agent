CREATE TABLE runs (
  id TEXT PRIMARY KEY,
  source_path TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  status TEXT NOT NULL,
  error_code TEXT,
  error_message TEXT,
  idempotency_key TEXT NOT NULL UNIQUE,
  request_fingerprint TEXT NOT NULL,
  lease_until REAL,
  heartbeat_at TEXT,
  worker_id TEXT,
  context_degraded INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE documents (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE CASCADE,
  page_count INTEGER NOT NULL,
  ast_version TEXT NOT NULL,
  source_metadata_json TEXT NOT NULL
);

CREATE TABLE segments (
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  id TEXT NOT NULL,
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chapter_id TEXT,
  page_number INTEGER NOT NULL,
  ordinal INTEGER NOT NULL,
  source_text TEXT NOT NULL,
  source_hash TEXT NOT NULL,
  bbox_refs_json TEXT NOT NULL,
  context_before_json TEXT NOT NULL,
  context_after_json TEXT NOT NULL,
  status TEXT NOT NULL,
  last_error TEXT,
  PRIMARY KEY (run_id, id),
  UNIQUE (run_id, ordinal)
);

CREATE TABLE translations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  segment_id TEXT NOT NULL,
  text TEXT NOT NULL,
  model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  context_version TEXT NOT NULL,
  attempt INTEGER NOT NULL,
  reason TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  is_current INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  FOREIGN KEY (run_id, segment_id) REFERENCES segments(run_id, id) ON DELETE CASCADE
);

CREATE TABLE entities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  entity_type TEXT NOT NULL CHECK (entity_type = 'person'),
  source_name TEXT NOT NULL,
  normalized_source_name TEXT NOT NULL,
  target_name TEXT NOT NULL,
  first_segment_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (run_id, entity_type, normalized_source_name)
);

CREATE TABLE entity_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  segment_id TEXT NOT NULL,
  source_name TEXT NOT NULL,
  observed_target_name TEXT NOT NULL,
  canonical_target_name TEXT NOT NULL,
  evidence_text TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (run_id, segment_id) REFERENCES segments(run_id, id) ON DELETE CASCADE
);

CREATE TABLE judgments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  segment_id TEXT NOT NULL,
  label TEXT NOT NULL CHECK (label IN ('ok','fidelity','coherence','entity','formatting','other')),
  notes TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'queued',
  created_at TEXT NOT NULL,
  processed_at TEXT,
  FOREIGN KEY (run_id, segment_id) REFERENCES segments(run_id, id) ON DELETE CASCADE
);

CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX idx_runs_status_lease ON runs(status, lease_until);
CREATE INDEX idx_segments_run_status ON segments(run_id, status, ordinal);
CREATE UNIQUE INDEX idx_translations_current ON translations(run_id, segment_id) WHERE is_current = 1;
CREATE INDEX idx_events_run ON events(run_id, id);

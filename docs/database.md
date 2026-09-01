# Database

## V1: SQLite

SQLite 是本地运行状态和人物 Entity Registry 的持久化层。原始 PDF、AST、译文、Judge 记录和渲染产物存放在 `runs/<run_id>/`，数据库只保存索引、状态和可查询元数据。

## Initial entities

### `runs`

`id`, `source_path`, `source_sha256`, `status`, `error_code`, `idempotency_key`, `request_fingerprint`, `glossary_json`, `lease_until`, `heartbeat_at`, `worker_id`, `created_at`, `updated_at`

`idempotency_key` 在同一本地 workspace 内唯一；`request_fingerprint` 包含输入 PDF hash、目标语言、Glossary hash 和配置版本。相同 key 且 fingerprint 相同的请求返回已有 run；fingerprint 不同则返回冲突错误。

`glossary_json` 是崩溃恢复源；`runs/<run_id>/glossary.json` 是可读 artifact，可从数据库原子重建。

### `documents`

`id`, `run_id`, `page_count`, `ast_version`, `source_metadata_json`

### `segments`

`id`, `document_id`, `chapter_id`, `ordinal`, `source_text`, `source_hash`, `bbox_refs_json`, `status`

### `translations`

`id`, `segment_id`, `text`, `model`, `prompt_version`, `context_version`, `attempt`, `is_current`, `created_at`

### `entities`

`id`, `run_id`, `entity_type`, `source_name`, `target_name`, `first_segment_id`, `created_at`, `updated_at`

V1 的 `entity_type` 只允许 `person`。同一 run 内 `source_name` 全局唯一；更新译名必须留下审计记录或产生新版本。

并发规则：对 `(run_id, entity_type, normalized_source_name)` 建立唯一索引；Entity upsert 必须在事务中执行。重复发现不得覆盖已有 `target_name`，而是记录 observation 并由 Workflow 采用已存在的 canonical 值。

### `judgments`

`id`, `segment_id`, `label`, `notes`, `created_at`

## Task claiming

SQLite 使用 WAL 模式。runner 领取任务时在短事务中写入 lease/heartbeat 字段；执行期间后台续租，超时 lease 可被恢复。translation、Entity、segment error 和 run 状态等关键写入必须校验当前 worker ownership，失租 worker 不得继续提交。所有写入必须经过 repository 层，Workflow 不直接拼接 SQL。

建议索引：`UNIQUE(idempotency_key)`、`INDEX(status, lease_until)`、`UNIQUE(run_id, entity_type, normalized_source_name)`。

Glossary 建议只保存为 `runs/<run_id>/glossary_suggestions.jsonl` artifact，不进入 V1 canonical 数据表；用户 Glossary 的输入 hash 写入 `runs.request_fingerprint`。

## Migration rule

使用 SQL migration 管理 SQLite schema。未来迁移 PostgreSQL 时保持领域表和 ID 语义不变，替换存储适配器，不让 Workflow 直接依赖 SQLite API。

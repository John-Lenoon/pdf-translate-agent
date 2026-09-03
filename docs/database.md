# Database

SQLite 是本地运行状态、任务协调和人物 Entity Registry 的 canonical store；原始 PDF、AST、译文、Judge 记录和渲染产物存放在 `runs/<run_id>/`。字段定义、约束和迁移 SQL 以 ORM/model 与 migration 代码及测试为真值。

## Domain relationships

一个 run 对应 document、segments、translations、entities、judgments，以及 V2 的 immutable model plan、candidate、risk decision 和 provider event 记录。候选按 segment 版本化，运行报告由 canonical records 和已验证 artifacts 重建，不是数据库真值。

## Invariants

- `idempotency_key` 在 workspace 内唯一；相同 fingerprint 的重复请求复用已有 run，冲突 fingerprint 明确失败。
- 同一 run 的人物 Entity 按 `(entity_type, normalized_source_name)` 唯一，且 V1/V2 只允许 `person`；并发 observation 必须按文档顺序在事务中合并，不覆盖既有 canonical 名称。
- runner 使用 WAL、短事务 lease/heartbeat 和 ownership 校验；失租 worker 不得继续写入，超时 lease 可恢复。
- 所有写入经过 repository 层；Workflow 不直接拼接 SQL。Glossary 输入 hash 和可恢复状态必须可追溯，artifact 使用临时文件原子替换。

## Index and migration strategy

保持 idempotency、状态领取和 Entity 唯一性所需的唯一索引/查询索引。使用 SQL migrations 管理 SQLite；未来迁移 PostgreSQL 时保持领域表和 ID 语义不变，仅替换存储适配器。

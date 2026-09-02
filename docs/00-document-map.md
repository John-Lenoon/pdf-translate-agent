# Document Map

本目录是项目文档的受控集合。AI 和开发者必须先阅读本索引，再按任务阅读对应文档；除项目负责人明确批准的路径外，不得新增、拆分、重命名、移动或归档 Markdown 文件。

## Source of truth

| 主题 | 唯一正式文档 | 内容边界 |
| --- | --- | --- |
| 产品范围与版本验收 | [`requirements.md`](requirements.md) / [`roadmap.md`](roadmap.md) | 目标、范围、版本状态和验收条件 |
| 系统结构 | [`architecture.md`](architecture.md) | 模块边界、运行进程和演进约束 |
| 翻译执行流程 | [`workflow.md`](workflow.md) | 状态机、段落处理、取消、恢复和渲染前置条件 |
| 模型合同 | [`ai.md`](ai.md) | Prompt、结构化输出、Entity、Glossary 和质量校验 |
| V2 双模型设计 | [`v2-dual-model.md`](v2-dual-model.md) | 本地小模型、远程审核、风险路由和运行报告 |
| 数据持久化 | [`database.md`](database.md) | SQLite 表、索引、迁移和恢复语义 |
| HTTP 接口 | [`api.md`](api.md) | FastAPI 请求、响应和错误码 |
| PDF 输出 | [`rendering.md`](rendering.md) | 坐标覆盖、字体、溢出、碰撞和输出校验 |
| 验证证据 | [`testing.md`](testing.md) | 测试矩阵、命令、结果、fixture 和限制 |
| 翻译质量评测 | [`../evals/README.md`](../evals/README.md) | Golden Set、V1/V2 对比、路由指标和发布门槛 |
| 实施顺序 | [`implementation.md`](implementation.md) | 开发切片、实施规则和升级边界 |
| 架构决策 | [`decisions.md`](decisions.md) | ADR、被拒绝方案和重新评估条件 |
| 代码审查 | [`review.md`](review.md) | Terra/Sol 审查范围和门槛 |
| Git 操作 | [`git.md`](git.md) | Commit、Push 和提交前检查 |

## Reading order

新功能先读 `requirements.md`、`roadmap.md` 和 `architecture.md`，再按影响范围阅读 `workflow.md`、`ai.md`、`database.md`、`api.md` 或 `rendering.md`。实现和验证分别遵循 `implementation.md`、`testing.md` 与 `git.md`。

## Version boundaries

- V1 的基线和验收以各正式契约中的 V1 小节为准。
- V2 的双模型行为以 `v2-dual-model.md` 为准；其他文档只保留必要的接口或数据引用，不复制完整 V2 规则。
- 早期讨论稿不属于当前规范，统一放在 `archive/`，仅用于追溯设计历史。

## Controlled history

`archive/` 只保存已经被正式设计取代的历史文档。归档文件不得作为实现依据；如果历史内容重新生效，必须先更新正式文档和 ADR。

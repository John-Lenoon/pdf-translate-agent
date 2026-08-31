# Roadmap

## Status vocabulary

`planned`, `in_progress`, `completed`, `blocked`, `deferred`。

只有验收标准和验证证据全部满足时，才能标记为 `completed`。

## V0 - 文档与骨架

Status: `in_progress`

### Requirements

- 建立仓库规则、架构、需求、Workflow、AI、API、数据库和评测文档。
- 建立 pnpm workspace 与 uv 的空项目骨架。
- 建立 V1 实施切片、验收和阻塞升级规则。

### Acceptance

- 文档互相链接且决策一致。
- `AGENTS.md` 明确测试、提交和完成状态规则。
- 文档中不存在未决的 V1 核心状态机、渲染失败或 Entity 并发规则。

## V1 - 本地翻译闭环

Status: `planned`

### Requirements

- 10 页以内数字文本型英文小说 PDF 完成端到端翻译。
- 初步支持 50 页以内，不承诺 SLA。
- PyMuPDF AST、自然段切分、人物 Entity、用户 Glossary、OpenAI Terra 翻译。
- 原页面覆盖中文译文并完成 overflow/碰撞检查。
- Next.js + FastAPI 本地网页支持进度、段落审阅和局部重译。
- 人工 Judge 不阻塞首次翻译。
- 首个垂直切片使用真实模型和 10 页以内 PDF，不使用 mock 翻译结果。

### Acceptance

- Golden Set 样本可重复运行并保存结果。
- 中断后可恢复，已完成 segment 不重复翻译。
- 人物名在全书范围内保持既定译名。
- 输出 PDF 不修改源文件，页面和结构要求可验证。
- 至少 3 个 10 页以内样本和至少 30 个 Golden Set 段落完成回归记录。
- 运行中断、取消、恢复和局部重译均有自动化测试证据。

## V2 - 质量增强

Status: `planned`

候选内容：实体别名/冲突、模型自动 Judge、Glossary 建议确认、章节级质量报告、更完善的阅读器。

## V3 - 规模化服务

Status: `planned`

候选内容：PostgreSQL、队列、对象存储、多用户、部署和 500 页性能验证。

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

Status: `in_progress`

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

### Current evidence

- 自动化实现覆盖解析、分段、Entity、结构化翻译、恢复、取消、局部重译和渲染失败检查。
- 最新证据：Python 27 passed、前端请求 3 passed、Next.js production build/TypeScript passed，桌面及 390 x 844 浏览器 UI 验收通过；详见 `docs/testing.md`。
- 高风险独立复审结论：`No blocking/high findings`。
- 尚未完成：使用有效 OpenAI 凭据运行 3 个合法的 10 页以内样本；建立并人工 Judge 至少 30 个 Golden Set 段落。
- 在上述证据全部满足前，V1 保持 `in_progress`，不得标记为 `completed`。

## V2 - 质量增强

Status: `planned`

### Requirements

- 本地小模型完成结构化初译；仅高风险 segment 由用户自带 key 的远程大模型进行局部审校或修订。
- 规则/QE 风险评分、远程 token 安全阈值、候选选择理由和模型/token/延迟记录可追溯。
- `TranslationCoordinator` 负责并发翻译和按文档顺序的 Entity 合并；`QualityRouter` 独占风险路由；`RunFinalizer` 在定稿后才调用渲染器。
- Provider Profile 的 API key 仅保存在操作系统凭据库，SQLite 和 `runs/` 只保存引用。
- 并发 Entity observation 按文档顺序合并；远程审校阈值或凭据问题产生明确的 `review_debt`，不得伪装为完整审校。
- 普通用户不参与 Judge；开发者从最终 PDF 与 `runs/` 产物审阅并可触发定向重译。

### Acceptance

- 50 页样本使用本地小模型完成首轮翻译；远程模型不接收整本 PDF 作为单段审校上下文。
- 任一远程修订的自动采用均具有 JSON、完整性、Entity、Glossary 和长度校验证据；失败不会静默覆盖本地候选。
- 远程 token 软阈值/硬上限会明确停止附加审校并报告受影响 segment，且不会泄露 API key。
- Provider Profile 必须经本地连通性测试后才能启用；凭据删除或恢复时不可解析会明确停止远程审校。
- 每次 run 固化不含 secret 的 `RunModelPlan`；本地 Ollama endpoint、模型存在性与结构化输出能力在启动前验证。
- `runs/<run_id>/run_report.json` 是版本化开发者审阅入口，包含审校债务、候选版本、风险决策、用量和渲染验证结果。
- 50 页性能结论附有目标机器、Ollama/模型版本、量化、并发、token、吞吐和内存使用的基准证据。
- V1 Golden Set 对比记录本地候选、远程修订和开发者审阅结论，用于校准风险阈值。

详细设计见 [`docs/v2-dual-model.md`](v2-dual-model.md)。

## V3 - 规模化服务

Status: `planned`

候选内容：PostgreSQL、队列、对象存储、多用户、部署和 500 页性能验证。

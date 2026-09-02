# Implementation Guide

本文档是 AI 和开发者执行 V1 的实施手册。它补充 `roadmap.md` 的版本目标，不替代 `requirements.md`、`workflow.md`、`testing.md` 或 `review.md`。

## Execution principles

- 使用真实 OpenAI Provider；不使用 mock 翻译冒充端到端完成。
- 首个垂直切片固定为 10 页以内的数字文本型英文小说 PDF。
- 每次只推进一个可验证的垂直切片，完成后再扩大范围。
- 代码改动由测试和实际样本验证；文档或代码未通过验收，不得把 roadmap 状态改为 `completed`。
- 不因为遇到困难就扩大技术范围、引入 V2 组件或改变已确认的架构边界。
- Terra 完成实现；只有命中 `docs/review.md` 的高风险改动才请求 Sol review。

## Documentation synchronization

每次修改代码、配置、API、数据结构、运行流程、用户界面或新增功能时，必须在同一变更中检查并更新受影响的 `docs/` 文档。文档更新不是收尾工作，而是功能变更的验收条件。

- 产品范围、版本目标或验收条件变化：更新 `requirements.md` 和 `roadmap.md`。
- 模块边界、状态机、模型合同、数据库、API 或渲染行为变化：分别更新 `architecture.md`、`workflow.md`、`ai.md`、`database.md`、`api.md` 或 `rendering.md`。
- 测试命令、验证结果或已知限制变化：更新 `testing.md`；不要在其他文档维护重复的测试数字。
- 技术选择或被否决方案变化：新增或更新 `decisions.md` 中的 ADR。
- 启动方式、环境变量、依赖版本或用户可见行为变化：同步更新 `README.md`。
- 翻译质量、模型路由、Prompt、Entity/Glossary 规则、渲染质量或评测指标变化：同步更新 `evals/README.md`，并说明需要重新运行的 Golden Set 或基准评测。
- 仅内部重构且不改变上述契约时，可不改文档，但必须在变更说明中明确判断为“无文档影响”。

提交前必须检查：文档中的环境变量、状态值、错误码、接口路径和验收数字是否仍能在代码或最新测试证据中找到对应来源。过时文档不得标记版本完成。

### Controlled document set

`docs/` 只允许维护已批准的文档文件：`00-document-map.md`、`requirements.md`、`roadmap.md`、`architecture.md`、`workflow.md`、`ai.md`、`database.md`、`api.md`、`rendering.md`、`testing.md`、`implementation.md`、`decisions.md`、`review.md`、`git.md`，以及已批准的历史文件 `archive/v2-discovery-notes.md` 和 `archive/local-model-integration-proposal.md`。AI 不得因为一次功能讨论或个人判断而新增、拆分、重命名、移动或归档 Markdown 文件。

确需新增文档（例如 `00-document-map.md` 或 `archive/` 下的历史文档）时，必须先获得项目负责人对“准确路径 + 用途”的明确批准；提出方案、在聊天中提到文件名或看到目录草图，都不等于批准。获批后才可以创建文件，并且必须同步更新文档索引和本节的白名单。能在现有文档中表达的内容，不得通过新增文件规避维护责任。

## V1 implementation slices

### Slice 1: Project and runtime skeleton

Deliver `pnpm` workspace, `uv` Python project, local environment instructions, and ignored run-artifact directories.

Acceptance: both toolchains install from a clean checkout; no secrets or generated artifacts are tracked.

### Slice 2: PDF AST and paragraph segmentation

Use PyMuPDF to parse a real <=10-page digital-text PDF into versioned page/block/line/span AST and stable natural-paragraph segments.

Acceptance: page count, text coverage, cross-page paragraphs, bbox references, and stable IDs are tested against a fixture.

### Slice 3: SQLite repository and resumable state

Implement migrations, repositories, idempotency keys, runner lease/heartbeat, entity uniqueness, and translation attempt persistence.

Acceptance: duplicate create/start requests are idempotent; runner restart reclaims expired work without duplicating valid translations.

### Slice 4: Real translation workflow

Connect the configured OpenAI model through a provider interface. Inject chapter summary, neighboring paragraphs, person Entity snapshot, and user Glossary. Persist structured output and model metadata.

Acceptance: a real 10-page fixture translates without per-segment user confirmation; schema failures and provider errors follow retry rules.

### Slice 5: Overlay renderer and validation

遮盖原文并在原区域绘制中文，执行字体、glyph、overflow、碰撞和 PDF 可读性检查。

Acceptance: source PDF remains unchanged; successful output is readable and failed pages are explicit failures, never silently omitted.

### Slice 6: Local API and review UI

Implement FastAPI endpoints and a Next.js local UI for run progress, page/segment navigation, Entity display, manual Judge labels, targeted retranslation, and artifact access.

Acceptance: user can start/resume a run, inspect a segment, submit a Judge decision, and retranslate only the selected segment.

### Slice 7: Golden Set regression

Create manually verified, rights-cleared alignment records from the selected English literary fixture. Keep full source material local; commit only permitted samples and metadata.

Acceptance: at least 30 accepted segment records can be rerun with fixed model, Prompt, AST, and context versions.

## Iteration budget and escalation

Agent 允许多次分析、修复和验证，但必须遵守以下边界：

1. 每个 slice 开始前先写清输入、输出和验收条件。
2. 每轮修改后立即运行该 slice 的最小验证，不把多个未验证问题叠在一起。
3. 连续两轮未能缩小失败范围，或需要改变架构边界时，暂停并标记 `blocked`，记录证据和待人工决策；不得自动无限循环。
4. 允许在同一 slice 内继续进行有明确新假设的尝试，但每次尝试必须记录“假设 → 证据 → 下一步”；没有新证据时停止重复尝试。
5. 发现 V2 需求时记录为 `deferred`，不在当前 slice 顺手实现。

## V2 implementation slices

V2 由项目负责人明确启动后，按以下独立切片实施；不得把未完成切片视为完整双模型工作流。

### Slice V2.1: Dual-model foundation

Deliver the local `OllamaAdapter`, `QualityRouter`, immutable `RunModelPlan`, candidate/risk/provider-event persistence, resumable review-debt queue state, and atomic developer `run_report.json`.

Acceptance: offline Adapter tests validate structured output; one `RoutingDecision` is persisted per segment; model plans cannot drift after run creation; a debt run can be reported and queued for explicit continuation.

### Slice V2.2: Profile and secure credential integration

Deliver local Provider Profile lifecycle and operating-system credential-vault Adapter. No browser, SQLite, artifact, or log may contain a secret.

Acceptance: a profile must pass connection testing before enablement; a deleted/unavailable credential produces `provider_credential_unavailable`; recovery does not fall back to environment credentials.

### Slice V2.3: Workflow integration and evaluation

Connect `TranslationCoordinator` and `RunFinalizer` to the existing runner, add remote-review idempotency, then validate a 50-page benchmark and Golden Set routing scorecard.

Acceptance: low-risk candidates complete locally; validated high-risk revisions are selected automatically; interruption cannot duplicate paid dispatch; performance and developer preference evidence is retained.

## Completion record

完成一个 slice 时，在 roadmap 或对应 ADR 中记录：变更文件、测试命令、真实 fixture、结果、已知限制和人工复核点。Git commit 由项目负责人手动创建。

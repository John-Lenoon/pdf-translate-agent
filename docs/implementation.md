# Implementation Guide

本文档是 AI 和开发者执行 V1 的实施手册。它补充 `roadmap.md` 的版本目标，不替代 `requirements.md`、`workflow.md` 或 `testing.md`。

## Execution principles

- 使用真实 OpenAI Provider；不使用 mock 翻译冒充端到端完成。
- 首个垂直切片固定为 10 页以内的数字文本型英文小说 PDF。
- 每次只推进一个可验证的垂直切片，完成后再扩大范围。
- 代码改动由测试和实际样本验证；文档或代码未通过验收，不得把 roadmap 状态改为 `completed`。
- 不因为遇到困难就扩大技术范围、引入 V2 组件或改变已确认的架构边界。

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

## Completion record

完成一个 slice 时，在 roadmap 或对应 ADR 中记录：变更文件、测试命令、真实 fixture、结果、已知限制和人工复核点。Git commit 由项目负责人手动创建。

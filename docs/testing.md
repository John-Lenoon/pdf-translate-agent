# Testing Matrix

## Unit tests

- PDF AST page/block/line/span schema and stable IDs
- Natural paragraph splitting across page boundaries
- Entity normalization, SQLite uniqueness, transaction/upsert behavior
- User Glossary injection and structured model output validation
- Workflow state transitions, retry limits, cancellation and lease recovery
- Overlay layout, missing glyph, overflow and collision detection
- Reflow title classification, image/vector-map extraction, source mapping, page-number merge and deterministic visual metrics
- Local/remote format review, review-debt handling and bounded chapter repair

## Integration tests

- A small digital-text PDF completes the full local workflow.
- Restarting the runner resumes without duplicate model calls.
- Manual Judge marks one segment and only that segment is retranslated.
- Source PDF hash change invalidates the run.

## UI checks

Verify progress, failed-page display, segment navigation, Entity display, Judge labels, retranslation action and artifact download with a local Next.js/FastAPI run. The Literary Editor Room theme must preserve readable serif translation text, stable scrollbar width during tab changes, visible keyboard focus, and no horizontal overflow at 390px and desktop widths.

## Evidence

Every completed roadmap item records the commands run, test result, fixture hash and any known limitations in the relevant version or ADR document.

## Latest V1 verification

- `scripts/python.ps1 -m pytest -q`: 27 passed。
- `node --test apps/web/test/*.test.mjs`: 3 passed。
- `pnpm --dir apps/web build`: production build 和 TypeScript passed。
- Literary Editor Room visual pass: warm paper palette, burgundy chapter accent, serif reading columns, stable scrollbar gutter and responsive layout; `pnpm --dir apps/web test` and production build passed。
- Browser：桌面与 390 x 844 移动视口通过 URL 恢复、失败状态、Resume 可用性、Review/Entity/Artifact 切换、无框架错误覆盖层、无 console error/warning；移动视口无横向页面 overflow。
- 独立高风险复审：`No blocking/high findings`。
- 已知外部阻塞：当前 OpenAI 凭据返回 authentication failure；尚无 3 个合法样本和 30 段人工 Golden Set 结果，因此 V1 不能标记 completed。

## Latest V2 verification

- `scripts/python.ps1 -m pytest -q`: 56 passed。
- `pnpm --dir apps/web test`: 3 passed；`pnpm --dir apps/web build` 通过。
- 覆盖范围：Ollama JSON-schema/视觉输入、确定性风险路由、模型计划、候选与审阅债务持久化、章节级 Chromium 重排、图片及矢量区域嵌入、模型标题判断、本地/远端格式审阅、两次上限的章节修复，以及视觉指标和格式报告。
- Chromium 产物已渲染为 PNG 并人工检查：中文正文、嵌入图像和单一全局页码可见，未见重叠。
- 未执行真实远端视觉模型和 50 页性能基准；它们属于后续运营验证，不影响本地可复现的 V2 自动化验收。

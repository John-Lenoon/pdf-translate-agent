# Testing Matrix

## Unit tests

- PDF AST page/block/line/span schema and stable IDs
- Natural paragraph splitting across page boundaries
- Entity normalization, SQLite uniqueness, transaction/upsert behavior
- User Glossary injection and structured model output validation
- Workflow state transitions, retry limits, cancellation and lease recovery
- Overlay layout, missing glyph, overflow and collision detection

## Integration tests

- A small digital-text PDF completes the full local workflow.
- Restarting the runner resumes without duplicate model calls.
- Manual Judge marks one segment and only that segment is retranslated.
- Source PDF hash change invalidates the run.

## UI checks

Verify progress, failed-page display, segment navigation, Entity display, Judge labels, retranslation action and artifact download with a local Next.js/FastAPI run.

## Evidence

Every completed roadmap item records the commands run, test result, fixture hash and any known limitations in the relevant version or ADR document.

## Latest V1 verification

- `scripts/python.ps1 -m pytest -q`: 27 passed。
- `node --test apps/web/test/*.test.mjs`: 3 passed。
- `pnpm --dir apps/web build`: production build 和 TypeScript passed。
- Browser：桌面与 390 x 844 移动视口通过 URL 恢复、失败状态、Resume 可用性、Review/Entity/Artifact 切换、无框架错误覆盖层、无 console error/warning；移动视口无横向页面 overflow。
- 独立高风险复审：`No blocking/high findings`。
- 已知外部阻塞：当前 OpenAI 凭据返回 authentication failure；尚无 3 个合法样本和 30 段人工 Golden Set 结果，因此 V1 不能标记 completed。

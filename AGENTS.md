# pdf-translate-agent

## Project rules

This repository builds a local, quality-focused literary PDF translation agent.
The V1 target is an unattended English-to-Chinese translation workflow for digital-text PDFs up to 50 pages, with a path to 500-page documents.

## Source of truth

- `README.md`: project purpose and local startup.
- `docs/requirements.md`: product scope and V1 acceptance criteria.
- `docs/architecture.md`: module boundaries and evolution plan.
- `docs/workflow.md`: translation state machine and artifact contracts.
- `docs/core-design.md`: model, routing, rendering, and failure contracts.
- `docs/database.md`: SQLite schema and future PostgreSQL migration notes.
- `docs/api.md`: local FastAPI contract.
- `docs/testing.md`: deterministic test and verification matrix.
- `docs/implementation.md`: bounded implementation slices and escalation rules.
- `docs/review.md`: scoped Terra/Sol review policy for high-risk changes.
- `docs/decisions.md`: ADRs and rejected alternatives.
- `docs/git.md`: commit convention, approval gates, and push policy.
- `docs/roadmap.md`: version goals, status, and acceptance checklists.
- `docs/00-document-map.md`: controlled document index and reading order.
- `evals/README.md`: Golden Set and quality regression process.

When documents conflict, `AGENTS.md` wins, followed by the most recent accepted ADR.

## Documentation synchronization

- `README.md` is the user entry point. When user-visible features, installation/startup commands, technology versions, environment variables, input/output formats, or V1/V2 scope and acceptance criteria change, update `README.md` in the same change.
- `evals/README.md` is the quality-evaluation entry point. When translation behavior, model routing, Entity/Glossary rules, prompts, risk policy, rendering quality, or evaluation metrics change, update the evaluation process in the same change.
- Internal refactors, test-only changes, and implementation details that do not affect users do not require README changes.
- Keep README concise and link to `docs/` for detail. If README and `docs/` conflict, resolve the conflict in the same change; do not leave contradictory instructions.

### Documentation file policy

- `docs/` is a controlled directory. Agents must not create, rename, move, split, or archive a Markdown file there on their own.
- The approved document set is: `00-document-map.md`, `requirements.md`, `roadmap.md`, `architecture.md`, `core-design.md`, `workflow.md`, `database.md`, `api.md`, `testing.md`, `implementation.md`, `decisions.md`, `review.md`, `git.md`, and the explicitly approved historical files `archive/v2-discovery-notes.md` and `archive/local-model-integration-proposal.md`.
- No other Markdown path under `docs/` may be created without explicit approval of that exact path and purpose. A discussion or plan is not approval to create a file.
- When a new document is approved, update the document map (or `README.md` until the map exists) and identify its single source-of-truth responsibility. Do not duplicate an existing document's contract.
- If a change can be documented in an approved file, update that file instead of adding a new one. If no approved file is suitable, stop and request approval before editing.

## Engineering constraints

- Use a pnpm workspace for JavaScript packages and `uv`/`pyproject.toml` for Python packages.
- Keep translation logic in Python. Next.js is the local review UI; it must not contain translation logic.
- V1 uses SQLite and the local filesystem. Do not add PostgreSQL, Redis, a hosted queue, OCR, or public deployment before an ADR approves it.
- Preserve the original PDF. Render a separate overlay translation PDF.
- V1 automatically manages person names only. User-provided Glossary entries are applied during translation; model Glossary suggestions are saved for post-run review and never block translation.
- The first translation run is unattended. Manual Judge review happens after completion and can enqueue targeted paragraph retranslation.
- Do not silently accept truncation, missing glyphs, or page-level render failures. Surface them as explicit run/segment errors.

## Change and verification rules

- Before editing, read the relevant docs and inspect existing changes. Never discard unrelated user work.
- Every code change must add or update focused tests. Documentation-only changes do not require runtime tests, but links and examples must be checked.
- Run the narrowest relevant tests, then the full suite before delivery when code is changed.
- 默认由项目负责人审阅改动。只有项目负责人在当前任务中明确同意后，Agent 才能执行授权范围内的 `git add`/`git commit`；“允许提交”不等于允许远程 push。执行 `git push` 前必须获得单独的明确授权，并确认 remote 和 branch。不得提交 secrets、生成的 PDF、本地数据库、`runs/` 产物或 `.env` 文件。
- A roadmap item is `completed` only when its acceptance criteria and verification evidence are satisfied. Otherwise use `in_progress`, `blocked`, or `deferred` and record why.

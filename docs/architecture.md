# Architecture

## Boundary

```text
Next.js local UI
        │ HTTP
FastAPI local API
        │
Workflow runner process ── SQLite + run artifacts
        ├─ Local Ollama Provider (V2)
        └─ Remote OpenAI-compatible Provider (V1/V2)
        │
PyMuPDF AST ── TranslationCoordinator ── QualityRouter ── Reflow renderer (Chromium + PyMuPDF)
                                      └─ Developer review / V1 Judge
```

Next.js 只负责本地任务控制和审阅界面。FastAPI 负责 API、任务状态和文件访问。Python Workflow 负责所有翻译领域逻辑。

FastAPI 和 Workflow runner 是两个本地进程。API 通过 SQLite 提交任务，runner 轮询并以事务方式领取任务；不在 HTTP 请求中执行长任务，也不依赖 FastAPI 的进程内 BackgroundTasks。

## Repository layout

```text
apps/web/       Next.js UI
apps/api/       FastAPI application
packages/       Shared schemas or UI utilities when needed
python/         Translation domain and workflow packages
evals/          Golden Set and evaluation tooling
docs/           Architecture and contracts
runs/           Ignored local run artifacts
```

## Local runtime

V1 手动启动三个进程：Next.js 开发服务器、FastAPI 和 Workflow runner。V2 沿用这三个进程，并在 runner 内通过 Provider Adapter 调用本地 Ollama 和按风险选择的远程 Provider。SQLite 是三者共享的唯一任务协调点；同一 `run_id` 同时只允许一个 runner。

## Evolution

V1/V2 先使用本地文件和 SQLite，验证 AST、人物一致性、双模型翻译闭环和中文阅读版 PDF 重排渲染。重排由 Chromium 分页，PyMuPDF 负责源图/地图区域提取、章节 PDF 合并、中文页码和确定性版面检查。只有当单机运行稳定且有明确 ADR 后，才评估 PostgreSQL、队列、对象存储和公网部署。

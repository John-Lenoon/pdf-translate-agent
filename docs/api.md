# Local API

## V2 extension

V2 adds local Provider Profile management and developer-only continuation controls. These are local configuration endpoints, not authentication or user-account endpoints. Secret values are accepted only by the local API for immediate storage in the operating-system credential vault and are never returned in responses.

- Provider Profile creation/update returns profile metadata and status only; `draft -> tested -> enabled` requires a connection test.
- Run creation selects enabled profile IDs. The API writes an immutable, secret-free `RunModelPlan` before queueing the run.
- Run status and artifact responses expose `completed_with_review_debt`, stable error codes, permitted next actions, and the versioned `run_report.json` path.
- A developer-only continuation action may queue only debt segments after a credential or remote-token condition is resolved. A normal user Judge endpoint is not part of the V2 product flow.

Exact URL shapes and request schemas must be specified with Pydantic before implementation. The API must never expose a credential-vault reference if it can be used to retrieve a secret outside the local process.

FastAPI 只在本机运行，为 Next.js 提供稳定边界。

## Initial endpoints

- `POST /runs`: 创建本地翻译任务
- `POST /runs/upload`: 通过 multipart 文件上传创建本地翻译任务
- `GET /runs/{run_id}`: 查询状态和进度
- `POST /runs/{run_id}/start`: 启动或恢复 Workflow
- `GET /runs/{run_id}/segments`: 获取段落及翻译状态
- `POST /runs/{run_id}/segments/{segment_id}/retranslate`: 标记并重译段落
- `GET /runs/{run_id}/entities`: 查看人物 Entity
- `GET /runs/{run_id}/artifacts`: 列出 AST、报告和 PDF 产物
- `POST /runs/{run_id}/cancel`: 请求取消任务
- `GET /runs/{run_id}/events`: 获取阶段和进度事件（V1 可先使用轮询，接口形状保持稳定）

API schema 使用 Pydantic。长任务由独立 Workflow runner 执行，接口只负责提交、查询和控制，不在请求中同步完成整本翻译。错误响应必须包含稳定的 `error_code`、用户可读 `message` 和 `run_id`/`segment_id`（若适用）。

`/runs/upload` 接收 `file`（PDF）、`idempotency_key` 和可选的 `glossary` JSON 字符串。上传文件保存到本地 `runs/uploads/` 并使用随机文件名；服务端校验 `.pdf` 扩展名和 PDF 文件头，不接受任意路径或非 PDF 文件。

V1 本地启动时允许手动分别运行 Next.js、FastAPI 和 runner；FastAPI 不得依赖进程内后台任务来保证长任务可靠性。

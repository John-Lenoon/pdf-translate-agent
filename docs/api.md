# Local API

FastAPI 只在本机运行，为 Next.js 提供稳定边界。

## Initial endpoints

- `POST /runs`: 创建本地翻译任务
- `GET /runs/{run_id}`: 查询状态和进度
- `POST /runs/{run_id}/start`: 启动或恢复 Workflow
- `GET /runs/{run_id}/segments`: 获取段落及翻译状态
- `POST /runs/{run_id}/segments/{segment_id}/retranslate`: 标记并重译段落
- `GET /runs/{run_id}/entities`: 查看人物 Entity
- `GET /runs/{run_id}/artifacts`: 列出 AST、报告和 PDF 产物
- `POST /runs/{run_id}/cancel`: 请求取消任务
- `GET /runs/{run_id}/events`: 获取阶段和进度事件（V1 可先使用轮询，接口形状保持稳定）

API schema 使用 Pydantic。长任务由独立 Workflow runner 执行，接口只负责提交、查询和控制，不在请求中同步完成整本翻译。错误响应必须包含稳定的 `error_code`、用户可读 `message` 和 `run_id`/`segment_id`（若适用）。

V1 本地启动时允许手动分别运行 Next.js、FastAPI 和 runner；FastAPI 不得依赖进程内后台任务来保证长任务可靠性。

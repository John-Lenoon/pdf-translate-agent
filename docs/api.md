# Local API

FastAPI 只在本机运行，为 Next.js 提供稳定边界。长任务由独立 Workflow runner 执行；API 只负责提交、查询和控制，不在请求中同步完成翻译。

## Boundary

API schema、请求/响应字段和枚举以 FastAPI/Pydantic 类型及自动生成的 OpenAPI 为唯一真值。运行服务后访问 `/docs`、`/redoc` 或 `/openapi.json` 查看当前契约。

端点按用途分为：创建/上传 run、查询状态与进度、启动/恢复、读取 segments/entities/artifacts/events、取消，以及 V1 Judge 触发的段落级重译。V2 还包括本地 Provider Profile 管理和仅开发者可用的 review-debt continuation；不提供认证或用户账户。

错误响应必须包含稳定的 `error_code`、用户可读 `message`，并在适用时包含 `run_id` 或 `segment_id`。密钥只由本地 API 接收后写入操作系统凭据库，响应不得返回 secret 或可独立取回 secret 的凭据引用。

上传接口只接受 PDF 文件，服务端校验扩展名和文件头，文件保存到本地 `runs/uploads/` 的随机文件名；不得接受任意路径。

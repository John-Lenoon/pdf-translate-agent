# pdf-translate-agent

一个本地运行、以翻译质量为核心的文学 PDF 翻译 Agent。

## V1 目标

V1 面向数字文本型英文小说 PDF，完成以下无人值守闭环：

```text
PDF → PyMuPDF 坐标 AST → 自然段切分 → 英译中
    → 人物 Entity 约束 → 原页面覆盖渲染 → 人工 Judge 复核
```

V1 首先验证 10 页以内的端到端闭环，初步支持 50 页以内的文档；500 页是后续容量目标，不设置 SLA。

## 技术栈

- Python、FastAPI、Pydantic、uv
- PyMuPDF
- SQLite
- OpenAI-compatible API（默认支持 OpenAI；可通过 `OPENAI_BASE_URL` 接入 DeepSeek 等兼容服务）
- Next.js、pnpm workspace

## V1 版本基线

以下版本是 V1 的目标运行基线。V1 不承诺兼容更低的大版本；`Slice 1` 完成后，实际验证过的版本将通过 `pyproject.toml`、`package.json`、`pnpm-lock.yaml` 和 `uv.lock` 固定。

| 组件 | V1 基线 |
| --- | --- |
| 操作系统 | Windows 11、macOS 13+ 或 Ubuntu 22.04+ |
| Node.js | 22.x LTS |
| pnpm | 10.x |
| Python | 3.13.x |
| uv | 0.11+ |
| Next.js | 16.x |
| React | 19.x |
| FastAPI | 0.116+ |
| Pydantic | 2.11+ |
| PyMuPDF | 1.26+ |
| SQLite | 3.47+ |
| OpenAI Python SDK | 1.100+ |

`TRANSLATION_MODEL` 必须填写当前 API 端点实际可调用的 model ID；设置 `OPENAI_BASE_URL` 后，Provider 使用兼容服务的 Chat Completions 结构化输出接口。依赖版本在实现阶段通过锁文件确认，未验证的组合不得标记为 V1 支持。

## 本地环境

需要 Node.js 22+、pnpm、Python 3.13+ 和 `uv`。在仓库根目录执行 `Copy-Item .env.example .env`，然后设置 `OPENAI_API_KEY` 与 `TRANSLATION_MODEL`；后端会自动加载这个文件，密钥只在本地环境变量中保存。可选的 `TRANSLATION_FONT_PATH` 可指向本机中文字体文件；未设置时使用 PyMuPDF 内置 CJK 字体。

V2 Runner 强制使用本地 Ollama：设置 `V2_LOCAL_MODEL=qwen3:8b` 和 `V2_OLLAMA_ENDPOINT=http://127.0.0.1:11434`；Ollama/GPU/probe 任一检查失败都会停止 Runner，不会回退到远程或 CPU。再设置 `V2_REMOTE_MODEL` 才会在高风险段落调用远程 Provider；当前临时沿用 `OPENAI_API_KEY`/`OPENAI_BASE_URL`，Provider Profile 与系统凭据库属于后续切片。默认关闭整章摘要（`V2_ENABLE_CHAPTER_SUMMARY=0`），本地请求默认限制为 4096 context / 512 输出 tokens，并关闭 Qwen3 thinking。

Next.js 默认连接 `http://127.0.0.1:8000`，无需前端环境文件。只有修改后端地址时，才执行 `Copy-Item apps/web/.env.local.example apps/web/.env.local` 并修改 `NEXT_PUBLIC_API_URL`。不要在 `NEXT_PUBLIC_*` 变量中放置 API 密钥，因为它们会进入浏览器端构建产物。

### 启动

推荐使用一条命令打开三个独立服务窗口：

```powershell
.\scripts\start-dev.ps1
```

脚本会检查 Python 依赖；如果前端依赖尚未安装，会自动执行安装，然后分别启动 FastAPI、Workflow runner 和 Next.js。关闭这三个窗口即可停止服务。也可以提前手动安装：

如果本机的 8000 或 3000 端口不可用，脚本会自动尝试后续端口；也可以显式指定端口，例如：

```powershell
.\scripts\start-dev.ps1 -ApiPort 8001 -WebPort 3001
```

```powershell
uv sync --extra dev
pnpm --dir apps/web install
```

如需完全手动启动，也可以在三个 PowerShell 终端中分别执行：

```powershell
uv sync --extra dev
pnpm --dir apps/web install

# 终端 1：FastAPI
.\scripts\python.ps1 -m uvicorn apps.api.main:app --reload --port 8000

# 终端 2：Workflow runner
.\scripts\python.ps1 -m translator.runner

# 终端 3：Next.js
pnpm --dir apps/web dev
```

`pnpm --dir apps/web dev` 表示在 `apps/web` 目录执行该包的 `dev` 脚本（即 `next dev`），等价于先进入该目录再运行 `pnpm dev`。根目录也提供快捷命令 `pnpm dev:web`。

浏览器访问 `http://localhost:3000`。在 `.env` 中设置 `OPENAI_API_KEY`、`OPENAI_BASE_URL`（例如 `https://api.deepseek.com`）和实际可调用的 `TRANSLATION_MODEL` 后，点击上传区域选择或拖入 PDF 即可创建任务；文件只保存到本地 `runs/uploads/`。

如果页面提示无法连接本地 API，请确认 FastAPI 终端仍在运行，并访问 `http://127.0.0.1:8000/health` 检查是否返回 `{"status":"ok"}`。

点击运行页的 `Cancel` 后，Runner 会在 250ms 内检测取消请求，并关闭正在进行的 Ollama 请求；当前段落不会写入译文，任务随后进入 `cancelled` 状态。

## 数据与版权

原始 PDF、完整翻译结果、本地 SQLite 数据库和运行产物均只保存在本地，不应提交到 Git。Golden Set 只能包含用户拥有合法使用权的 JSON 对齐片段或脱敏元数据；未经授权的文学原文和译文不得上传到本仓库。用户必须确认自己有权处理输入文档。项目不会将文件上传到作者服务器，但翻译文本可能发送到用户配置的第三方模型 API，请根据相应服务条款和版权要求使用。

## 文档

文档阅读入口见 [`docs/00-document-map.md`](docs/00-document-map.md)，其中列出了 V1/V2 的唯一来源和阅读顺序。开发 Agent 规则见 [`AGENTS.md`](AGENTS.md)。Git 提交规范见 [`docs/git.md`](docs/git.md)。质量评测流程见 [`evals/README.md`](evals/README.md)。

## 当前状态

V1 本地闭环已进入 `in_progress`：自动化实现、本地 UI 与高风险代码审查已通过，但正式完成仍取决于真实模型可用性、3 个合法样本和至少 30 个 Golden Set 段落的人工 Judge 记录。当前状态和证据以 [`docs/roadmap.md`](docs/roadmap.md) 为准。

V2 双模型基础层已进入 `in_progress`：包含本地 Ollama Adapter、可解释风险路由、不可变模型计划、候选/风险持久化和开发者运行报告。Provider Profile UI、操作系统凭据库以及对 V1 Workflow 的双模型接入仍未完成。V2 保持本地优先，不引入登录、多用户托管、PostgreSQL 或通用 RAG；详细边界见 [`docs/v2-dual-model.md`](docs/v2-dual-model.md)。

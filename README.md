# PDF Translate Agent

一个本地优先的英文小说 PDF 翻译工具。它将数字文本型 PDF 翻译为中文阅读版 PDF：本地小模型完成首轮翻译，远程大模型只处理高风险段落和可疑版面页，以减少成本并保持中文阅读质量。

原始 PDF 始终保留不变。默认输出保持原纸张尺寸，但中文可以自然增加页数；正文固定为 13pt，不会为塞回英文原页而缩小。原图、插图和矢量地图/图表会进入新的中文排版流。

## 功能概览

- 英文数字文本 PDF 到简体中文，首次翻译无需逐段确认。
- 本地 Ollama 初译，可选 OpenAI-compatible 远程复审和修订。
- 人物译名一致性、用户 Glossary、章节摘要和相邻段落上下文。
- Chromium 中文阅读版重排：章节换页、首行缩进、全局页码、图片和地图保留。
- 确定性版面检查加本地/远端格式审阅；失败时最多自动重排受影响章节两次。
- 浏览器内嵌预览、下载 PDF，以及下载可审计的运行报告。

## 适用范围

当前适合可提取文字的英文现代小说 PDF。扫描件、OCR、复杂表单、受 DRM 保护的文件和逐像素复刻原书版式不在支持范围内。建议先使用 10 页以内文件验证本机环境；50 页以上应先完成自己的性能和质量评估。

## 系统要求

| 组件 | 推荐版本 | 用途 |
| --- | --- | --- |
| Windows 11、macOS 13+ 或 Ubuntu 22.04+ | 当前支持平台 | 本地运行 |
| Python | 3.12+ | 翻译、PDF 和 API 服务 |
| [uv](https://docs.astral.sh/uv/) | 最新稳定版 | Python 环境与依赖 |
| Node.js | 22 LTS | Web UI 与 Chromium 工具 |
| [pnpm](https://pnpm.io/installation) | 10+ | JavaScript 依赖 |
| [Ollama](https://ollama.com/) | 最新稳定版，可选 | 本地首轮翻译 |
| OpenAI-compatible API key | 可选 | 高风险文本和版面远程复审 |

首次使用 reflow 阅读版还需要下载 Playwright Chromium，约需要额外磁盘空间。建议安装可显示中文的字体；未配置时会按 `Noto Serif CJK SC`、`Source Han Serif SC`、`SimSun` 和系统 serif 回退。

## 快速开始

以下命令以 PowerShell 为例；macOS/Linux 将 `Copy-Item` 替换为 `cp`，脚本可改用下方的手动启动命令。

```powershell
git clone <repository-url> pdf-translate-agent
Set-Location pdf-translate-agent

Copy-Item .env.example .env
uv sync --extra dev
pnpm install
pnpm exec playwright install chromium
```

然后按 [配置模型](#配置模型) 修改 `.env`，并启动三个本地进程：

```powershell
.\scripts\start-dev.ps1
```

脚本会分别打开 FastAPI、Workflow Runner 和 Next.js 窗口。浏览器访问脚本打印的 `http://localhost:<port>`，上传 PDF，创建任务后点击启动。默认端口为 API `8000`、网页 `3000`；端口占用时脚本会选择之后的可用端口，也可显式指定：

```powershell
.\scripts\start-dev.ps1 -ApiPort 8001 -WebPort 3001
```

启动后可确认 API 可用：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

预期返回包含 `"status": "ok"` 的 JSON。关闭三个服务窗口即可停止本地服务。

## 配置模型

所有配置放在仓库根目录 `.env`，该文件不应提交。复制 `.env.example` 后，从以下两种模式任选其一。

### 推荐：本地初译加远程复审

先安装并启动 Ollama，然后下载与 `.env` 对应的模型：

```powershell
ollama pull qwen3:8b
ollama serve
```

若 Ollama 已作为桌面程序或系统服务运行，只需要执行 `ollama pull`。在 `.env` 中设置：

```dotenv
# 本地首轮翻译
V2_LOCAL_MODEL=qwen3:8b
V2_OLLAMA_ENDPOINT=http://127.0.0.1:11434
V2_LOCAL_CONTEXT_WINDOW=4096
V2_LOCAL_MAX_OUTPUT_TOKENS=512

# 远程高风险文本与格式复审。兼容 OpenAI Chat Completions 的服务也可使用。
OPENAI_API_KEY=your_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
TRANSLATION_MODEL=your-remote-model-id
# 可选；空值时使用 TRANSLATION_MODEL。
V2_REMOTE_MODEL=
```

Runner 启动时会探测 Ollama 服务、模型存在性、GPU 载入状态和结构化输出能力。探测失败时不会悄悄退回到 CPU 或另一个模型，而会在 Runner 窗口说明原因。若希望本地模型完成页面格式审阅，应选择支持图像输入的 Ollama 模型；纯文本模型仍可完成翻译，但其页面审阅失败会明确记为 `format_review_debt`。

本地模型会处理首轮翻译。远程模型只接收高风险段落的有界上下文和需要复审的页面截图，不会把整本 PDF 当作一个请求发送。远程调用失败、超时或未配置时，任务会保留有效 PDF，并标记 `completed_with_review_debt` 或在报告中记录 `format_review_debt`。

### 仅使用远程模型

不使用 Ollama 时清空 `V2_LOCAL_MODEL`：

```dotenv
V2_LOCAL_MODEL=
OPENAI_API_KEY=your_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
TRANSLATION_MODEL=your-remote-model-id
```

此模式由远程模型直接完成翻译，适合先验证 API 配置。请注意文本会发送至你指定的模型服务。

### OpenAI-compatible 服务

将 `OPENAI_BASE_URL` 改为服务商 API 根地址，并把 `TRANSLATION_MODEL` 设置为该服务实际可调用的模型 ID。例如某些服务使用：

```dotenv
OPENAI_BASE_URL=https://api.example.com/v1
TRANSLATION_MODEL=provider-model-id
```

不同服务对 JSON schema、视觉输入和模型名称的支持不同。先用小型、无敏感内容的 PDF 测试，再处理正式文档。

### 排版与字体

```dotenv
# 默认值。reflow 是中文阅读版；overlay 是旧版坐标覆盖，适合回归比较。
V2_RENDER_MODE=reflow
V2_REFLOW_FONT_FAMILY=Noto Serif CJK SC, Source Han Serif SC, SimSun, serif

# 可选：嵌入本机字体。Windows 路径建议使用正斜杠。
TRANSLATION_FONT_PATH=C:/Windows/Fonts/simsun.ttc
```

配置自定义字体后，渲染器会验证路径。正文不会因排版拥挤而缩小；应优先检查翻译长度、图像尺寸或章节布局，而不是降低字号。

### 风险路由参数

```dotenv
V2_REMOTE_RISK_THRESHOLD=0.35
V2_CONTEXT_DEGRADED_WEIGHT=0.35
V2_CALIBRATION_INTERVAL=5
```

这些值控制远程复审覆盖率和抽检频率。不要只凭主观感觉调高或调低；修改前后应在同一 Golden Set 上比较质量、远程 token 和 review debt，详见 [`evals/README.md`](evals/README.md)。

## 首次翻译与产物

网页上传后，Runner 处理任务。完成时可在网页直接预览和下载 `translated.pdf`。本地 `runs/<run_id>/` 还包含：

| 产物 | 内容 |
| --- | --- |
| `translated.pdf` | 中文阅读版 PDF |
| `translated.report.json` | 输出页映射、确定性验证和格式审阅结果 |
| `format_review.json` | 每页视觉指标、截图、模型审阅事件、usage 和修复历史 |
| `reflow_document.json` | 章节、源段落、图片和标题结构判断 |
| `reflow-assets/` | 从源 PDF 提取的图片和矢量区域截图 |
| `reflow-preview/` | 格式审阅使用的页面 PNG |
| `run_report.json` | 模型计划、候选、风险路由、用量和审阅债务 |

`completed` 表示翻译和已配置的审阅步骤已完成。`completed_with_review_debt` 表示 PDF 可用，但有远程文本或格式审阅未完成，必须通过报告确认原因。`render_failed`、`failed` 或明确的 segment 错误不能视为成功产物。

## 手动启动与命令行诊断

当一键启动失败时，在三个终端分别运行：

```powershell
# 终端 1：API
.\scripts\python.ps1 -m uvicorn apps.api.main:app --reload --port 8000

# 终端 2：后台处理器
.\scripts\python.ps1 -m translator.runner

# 终端 3：网页
pnpm --dir apps/web dev --port 3000
```

Runner 处理当前任务后退出，可用于 CI 或故障定位：

```powershell
.\scripts\python.ps1 -m translator.runner --once
```

网页默认连接 `http://127.0.0.1:8000`。只有 API 使用非默认地址时才创建 `apps/web/.env.local`：

```powershell
Copy-Item apps/web/.env.local.example apps/web/.env.local
```

并设置 `NEXT_PUBLIC_API_URL=http://127.0.0.1:<api-port>`。不要把任何 API key 放入 `NEXT_PUBLIC_*` 变量，它们会进入浏览器产物。

## 常见问题

### `Runner readiness failed` 或找不到 Ollama 模型

确认 `ollama serve` 可访问、`V2_OLLAMA_ENDPOINT` 正确，并运行 `ollama list` 检查 `.env` 中的 `V2_LOCAL_MODEL` 是否已下载。GPU 检查失败时，先确认 Ollama 的模型进程已加载到 GPU；不要把该错误当作普通网络错误忽略。

### Playwright 或 Chromium 错误

在仓库根目录重新执行：

```powershell
pnpm install
pnpm exec playwright install chromium
```

阅读版依赖 Chromium。暂时需要比较旧版坐标覆盖时可设 `V2_RENDER_MODE=overlay`，但它不具备中文自然增页的阅读体验。

### 网页无法连接 API

确认 API 窗口还在运行，检查 `http://127.0.0.1:8000/health`，并确认 `NEXT_PUBLIC_API_URL` 与实际 API 端口一致。`start-dev.ps1` 在端口冲突时会打印最终端口。

### 中文变成方框、字体路径错误或排版异常

安装支持简体中文的字体，或设置有效的 `TRANSLATION_FONT_PATH`。查看 `format_review.json` 中的 `hard_issues`、每页 `min_font_size`、截图和 `repair_history`；不得通过缩小正文字号掩盖问题。

### 远程审阅债务

查看 `run_report.json` 和 `format_review.json` 的 provider events。常见原因是 API key、网络、模型不支持结构化/视觉输入、或远程额度限制。债务是显式状态，不能当作远程复审已经通过。

## 验证与贡献

修改代码前后运行：

```powershell
.\scripts\python.ps1 -m pytest -q
pnpm --dir apps/web test
pnpm --dir apps/web build
```

渲染、模型路由、格式检查和评测规则发生变化时，同时更新 [`evals/README.md`](evals/README.md)。项目架构、工作流、测试和版本边界见 [`docs/00-document-map.md`](docs/00-document-map.md)。

## 数据、隐私与版权

源 PDF、译文、SQLite 数据库和运行产物默认存放在本机 `runs/`，不应提交到 Git。项目不会将文件上传到作者服务器；但使用远程模型时，相关翻译文本、有限上下文以及必要时的可疑页面截图会发送给你配置的服务商。请确认你拥有处理文档的合法权利，并遵守模型服务条款、版权和隐私要求。

OCR、托管部署、多用户账户、操作系统凭据库、Provider Profile UI 和经过验证的 50 页性能基准不在当前开源版本范围内。

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
- OpenAI API（模型通过 `TRANSLATION_MODEL` 配置；Terra 是当前选定的模型系列）
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

`TRANSLATION_MODEL` 必须填写实际可调用的 OpenAI API model ID；“Terra”不是可直接复制到配置中的版本号或 model ID。依赖版本在实现阶段通过锁文件确认，未验证的组合不得标记为 V1 支持。

## 本地环境

需要 Node.js 22+、pnpm、Python 3.13+ 和 `uv`。复制 `.env.example` 为 `.env`，设置 `OPENAI_API_KEY` 与 `TRANSLATION_MODEL`；密钥只在本地环境变量中保存。

V1 计划手动启动三个本地进程：Next.js UI、FastAPI API 和 Python Workflow runner。具体命令会在对应实现切片完成后补充；当前仓库仍处于文档阶段。

## 数据与版权

原始 PDF、完整翻译结果、本地 SQLite 数据库和运行产物均只保存在本地，不应提交到 Git。Golden Set 只能包含用户拥有合法使用权的 JSON 对齐片段或脱敏元数据；未经授权的文学原文和译文不得上传到本仓库。用户必须确认自己有权处理输入文档。项目不会将文件上传到作者服务器，但翻译文本可能发送到用户配置的第三方模型 API，请根据相应服务条款和版权要求使用。

## 文档

架构和版本验收标准见 [`docs/`](docs/)。开发 Agent 规则见 [`AGENTS.md`](AGENTS.md)。Git 提交规范见 [`docs/git.md`](docs/git.md)。质量评测流程见 [`evals/README.md`](evals/README.md)。

## 当前状态

项目处于文档和架构定义阶段，尚未开始实现代码。
